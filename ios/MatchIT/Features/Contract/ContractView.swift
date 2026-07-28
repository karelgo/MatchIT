import Observation
import SwiftUI

@MainActor
@Observable
final class ContractViewModel {
    let matchId: UUID
    let isCompany: Bool

    var contract: Contract?
    var evidencePack: EvidencePack?
    var showingEvidencePack = false
    var hourlyRate = ""
    var hoursPerWeek = 40
    var startDate = Date()
    var isLoading = false
    var isBusy = false
    var errorMessage: String?

    private let api: APIClient

    init(api: APIClient, matchId: UUID, isCompany: Bool) {
        self.api = api
        self.matchId = matchId
        self.isCompany = isCompany
    }

    var canDraft: Bool { Double(hourlyRate) ?? 0 > 0 && !isBusy }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            contract = try await api.contract(matchId: matchId)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func draft() async {
        guard let rate = Double(hourlyRate), rate > 0 else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            contract = try await api.createContract(
                matchId: matchId,
                hourlyRate: rate,
                currency: "EUR",
                hoursPerWeek: hoursPerWeek,
                startDate: Self.isoDay.string(from: startDate),
                endDate: nil
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func sign() async {
        isBusy = true
        defer { isBusy = false }
        do {
            contract = try await api.signContract(matchId: matchId)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Assemble the engagement evidence pack — contract, scope, invoices, signature
    /// trail and the independence indicators — as one document to hand to an adviser.
    func loadEvidencePack() async {
        isBusy = true
        defer { isBusy = false }
        do {
            evidencePack = try await api.evidencePack(matchId: matchId)
            showingEvidencePack = evidencePack != nil
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// The API takes calendar dates, not instants — format in UTC so a late-evening
    /// local time cannot roll the start date back a day.
    static let isoDay: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}

struct ContractView: View {
    @State private var model: ContractViewModel

    init(api: APIClient, matchId: UUID, isCompany: Bool) {
        _model = State(
            initialValue: ContractViewModel(api: api, matchId: matchId, isCompany: isCompany)
        )
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let message = model.errorMessage {
                    ErrorBanner(message: message)
                }
                if model.isLoading {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                } else if let contract = model.contract {
                    statusCard(contract)
                    documentCard(contract)
                    signatureCard(contract)
                    evidenceCard
                } else if model.isCompany {
                    termsForm
                } else {
                    ContentUnavailableView(
                        "No contract yet",
                        systemImage: "doc.text",
                        description: Text("The company drafts the contract once you've matched.")
                    )
                }
            }
            .padding(Theme.screenPadding)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Contract")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .sheet(isPresented: $model.showingEvidencePack) {
            if let pack = model.evidencePack {
                EvidencePackSheet(pack: pack)
            }
        }
    }

    /// The file you want before anyone asks for it. Offered from the moment the
    /// contract exists rather than when a letter arrives.
    private var evidenceCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Engagement evidence pack", systemImage: "folder.badge.person.crop")
                .font(.system(.headline, design: .rounded))
            Text(
                "Contract, scope, invoices, signature trail and the independence indicators, assembled as one document for your adviser."
            )
            .font(.caption)
            .foregroundStyle(.secondary)
            Button {
                Task { await model.loadEvidencePack() }
            } label: {
                if model.isBusy {
                    ProgressView()
                } else {
                    Label("Assemble the pack", systemImage: "doc.text.magnifyingglass")
                        .font(.subheadline.weight(.semibold))
                }
            }
            .disabled(model.isBusy)
        }
        .padding()
        .cardStyle()
    }

    private var termsForm: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Agree the terms", systemImage: "doc.badge.plus")
                .font(.system(.title3, design: .rounded, weight: .semibold))
            Text("The AI drafts from these terms — it never invents a rate or a date.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            HStack {
                Text("Hourly rate")
                Spacer()
                TextField("120", text: $model.hourlyRate)
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.trailing)
                    .frame(width: 90)
                Text("EUR").foregroundStyle(.secondary)
            }
            Stepper("\(model.hoursPerWeek) hours/week", value: $model.hoursPerWeek, in: 4 ... 60, step: 4)
            DatePicker("Start date", selection: $model.startDate, displayedComponents: .date)
            Button {
                Task { await model.draft() }
            } label: {
                if model.isBusy { ProgressView().tint(.white) } else { Text("Draft the contract") }
            }
            .buttonStyle(.primary)
            .disabled(!model.canDraft)
        }
        .padding()
        .cardStyle()
    }

    private func statusCard(_ contract: Contract) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(contract.draft.title)
                    .font(.system(.title3, design: .rounded, weight: .semibold))
                Spacer()
                if contract.isActive {
                    Image(systemName: "checkmark.seal.fill").foregroundStyle(Theme.success)
                }
            }
            HStack(spacing: 16) {
                Label(
                    "\(Int(contract.hourlyRate)) \(contract.currency)/h", systemImage: "eurosign.circle"
                )
                Label("\(contract.hoursPerWeek) h/week", systemImage: "clock")
            }
            .font(.caption.weight(.medium))
            .foregroundStyle(.secondary)
            Text(contract.isActive ? "Signed by both parties" : "Awaiting signatures")
                .font(.caption)
                .foregroundStyle(contract.isActive ? Theme.success : .secondary)
        }
        .padding()
        .cardStyle()
    }

    private func documentCard(_ contract: Contract) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            section("Scope of work", items: contract.draft.scopeOfWork)
            labelled("Rate & invoicing", contract.draft.rateTerms)
            labelled("Duration", contract.draft.durationTerms)
            ForEach(contract.draft.clauses, id: \.heading) { clause in
                labelled(clause.heading, clause.body)
            }
            labelled("Governing law", contract.draft.governingLaw)

            if !contract.draft.openPoints.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Label("Open points", systemImage: "exclamationmark.triangle.fill")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.orange)
                    ForEach(contract.draft.openPoints, id: \.self) { point in
                        Text("• \(point)").font(.caption).foregroundStyle(.secondary)
                    }
                }
                .padding(10)
                .background(Color.orange.opacity(0.12), in: .rect(cornerRadius: 10))
            }

            Text(
                "This is an AI-generated draft, not legal advice. Have it reviewed before signing."
            )
            .font(.caption2)
            .foregroundStyle(.tertiary)
        }
        .padding()
        .cardStyle()
    }

    private func signatureCard(_ contract: Contract) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                signatureRow("Company", signed: contract.companySigned)
                Spacer()
                signatureRow("Specialist", signed: contract.specialistSigned)
            }
            if contract.awaitingMySignature {
                Button {
                    Task { await model.sign() }
                } label: {
                    if model.isBusy { ProgressView().tint(.white) } else { Text("Sign contract") }
                }
                .buttonStyle(.primary)
                .disabled(model.isBusy)
            } else if !contract.isActive {
                Text("You've signed. Waiting for the other party.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .cardStyle()
    }

    private func signatureRow(_ title: String, signed: Bool) -> some View {
        Label(title, systemImage: signed ? "checkmark.circle.fill" : "circle")
            .font(.subheadline)
            .foregroundStyle(signed ? Theme.success : .secondary)
    }

    private func section(_ title: String, items: [String]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.subheadline.weight(.semibold))
            ForEach(items, id: \.self) { item in
                Text("• \(item)").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func labelled(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.subheadline.weight(.semibold))
            Text(body).font(.caption).foregroundStyle(.secondary)
        }
    }
}
