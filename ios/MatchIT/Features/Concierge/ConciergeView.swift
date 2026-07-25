import SwiftUI

struct ConciergeView: View {
    @State private var model: ConciergeViewModel

    init(api: APIClient) {
        _model = State(initialValue: ConciergeViewModel(api: api))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    if let message = model.errorMessage {
                        ErrorBanner(message: message)
                    }
                    switch model.phase {
                    case .needsCompanyProfile: companyForm
                    case .describing: describeCard
                    case let .reviewing(assignment): reviewCard(assignment)
                    case let .matched(_, matches): matchList(matches)
                    }
                }
                .padding(Theme.screenPadding)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Concierge")
            .task { await model.bootstrap() }
        }
    }

    private var companyForm: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("First, tell us who's hiring")
                .font(.system(.title3, design: .rounded, weight: .semibold))
            TextField("Company name", text: $model.companyName)
            TextField("Industry (optional)", text: $model.companyIndustry)
            Button("Continue") { Task { await model.saveCompanyProfile() } }
                .buttonStyle(.primary)
                .disabled(model.isBusy)
        }
        .textFieldStyle(.roundedBorder)
        .padding()
        .cardStyle()
    }

    private var describeCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Describe your problem", systemImage: "sparkles")
                .font(.system(.title3, design: .rounded, weight: .semibold))
            Text("Talk to us like you'd talk to a colleague. The AI writes the assignment.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            TextEditor(text: $model.problemText)
                .frame(minHeight: 160)
                .padding(8)
                .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 12))
                .accessibilityLabel("Problem description")
            Text("Example: “We need two Microsoft Fabric architects to migrate our data warehouse within six months.”")
                .font(.caption)
                .foregroundStyle(.tertiary)
            Button {
                Task { await model.submitProblem() }
            } label: {
                if model.isBusy { ProgressView().tint(.white) } else { Text("Let AI write the assignment") }
            }
            .buttonStyle(.primary)
            .disabled(!model.canSubmitDescription || model.isBusy)
        }
        .padding()
        .cardStyle()
    }

    private func reviewCard(_ assignment: Assignment) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Your assignment", systemImage: "doc.text.magnifyingglass")
                .font(.system(.title3, design: .rounded, weight: .semibold))
            Text(assignment.requirements.summary)
                .font(.body)

            ForEach(assignment.requirements.roles, id: \.self) { role in
                VStack(alignment: .leading, spacing: 8) {
                    Text("\(role.count)× \(role.title) · \(role.seniority.capitalized)")
                        .font(.headline)
                    ChipFlow(items: role.mustHaveSkills.map(\.capitalized))
                    if !role.niceToHaveSkills.isEmpty {
                        ChipFlow(items: role.niceToHaveSkills.map { "+ \($0.capitalized)" })
                    }
                }
                .padding(12)
                .background(Theme.accentSoft, in: .rect(cornerRadius: 12))
            }

            if let max = assignment.requirements.budget.maxHourly {
                Label(
                    "Budget up to \(Int(max)) \(assignment.requirements.budget.currency)/hour",
                    systemImage: "eurosign.circle"
                )
                .font(.subheadline)
            }

            if !assignment.requirements.clarifyingQuestions.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("The AI would also like to know:")
                        .font(.subheadline.weight(.semibold))
                    ForEach(assignment.requirements.clarifyingQuestions, id: \.self) { question in
                        Label(question, systemImage: "questionmark.circle")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Button {
                Task { await model.findSpecialists() }
            } label: {
                if model.isBusy { ProgressView().tint(.white) } else { Text("Find specialists") }
            }
            .buttonStyle(.primary)
            .disabled(model.isBusy)
        }
        .padding()
        .cardStyle()
    }

    private func matchList(_ matches: [Match]) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Ranked specialists")
                    .font(.system(.title3, design: .rounded, weight: .semibold))
                Spacer()
                Button("New search") { model.startOver() }
                    .font(.subheadline)
            }
            if matches.isEmpty {
                ContentUnavailableView(
                    "No specialists yet",
                    systemImage: "person.2.slash",
                    description: Text("As specialists join, matches will appear here instantly.")
                )
            }
            ForEach(matches) { match in
                CandidateCard(match: match) { decision in
                    Task { await model.decide(match: match, decision: decision) }
                }
            }
        }
    }
}

struct CandidateCard: View {
    let match: Match
    let onDecision: (MatchDecision) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                ScoreRing(score: match.score).frame(width: 54, height: 54)
                VStack(alignment: .leading, spacing: 4) {
                    Text(match.specialist.headline)
                        .font(.headline)
                    Text(
                        "\(match.specialist.yearsExperience) yrs · \(match.specialist.country) · \(match.specialist.remotePreference.displayName)"
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    if let rate = match.specialist.hourlyRate {
                        Text("\(Int(rate)) \(match.specialist.currency)/hour")
                            .font(.caption.weight(.medium))
                    }
                }
                Spacer()
            }
            ChipFlow(items: match.specialist.skills.prefix(5).map { $0.name.capitalized })

            if match.status == "mutual" {
                Label("It's a match — chat unlocked", systemImage: "checkmark.seal.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.success)
            } else if match.companyDecision == .pending {
                HStack(spacing: 10) {
                    Button {
                        onDecision(.rejected)
                    } label: {
                        Label("Pass", systemImage: "xmark")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    Button {
                        onDecision(.accepted)
                    } label: {
                        Label("Shortlist", systemImage: "checkmark")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Theme.accent)
                }
            } else {
                Text(match.companyDecision == .accepted ? "Shortlisted — waiting for the specialist" : "Passed")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .cardStyle()
    }
}
