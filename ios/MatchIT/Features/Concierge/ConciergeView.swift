import SwiftUI

struct ConciergeView: View {
    @State private var model: ConciergeViewModel
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
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

            estimateRows(assignment.requirements)

            if assignment.requirements.clarifyingQuestions.isEmpty {
                Label("The concierge has everything it needs", systemImage: "checkmark.seal")
                    .font(.caption)
                    .foregroundStyle(Theme.success)
            } else {
                conciergeThread(assignment)
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

    @ViewBuilder
    private func estimateRows(_ requirements: AssignmentRequirements) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let max = requirements.budget.maxHourly {
                HStack(spacing: 6) {
                    Label(
                        "Budget up to \(Int(max)) \(requirements.budget.currency)/hour",
                        systemImage: "eurosign.circle"
                    )
                    if requirements.budgetIsEstimated { EstimateBadge() }
                }
            }
            if let weeks = requirements.durationWeeks {
                HStack(spacing: 6) {
                    Label("Duration about \(weeks) weeks", systemImage: "calendar")
                    if requirements.durationIsEstimated { EstimateBadge() }
                }
            }
        }
        .font(.subheadline)
    }

    private func conciergeThread(_ assignment: Assignment) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("The concierge would like to know:")
                .font(.subheadline.weight(.semibold))
            ForEach(assignment.requirements.clarifyingQuestions, id: \.self) { question in
                Label(question, systemImage: "questionmark.circle")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 8) {
                TextField("Answer in your own words…", text: $model.answerText, axis: .vertical)
                    .lineLimit(1 ... 4)
                    .textFieldStyle(.roundedBorder)
                Button {
                    Task { await model.sendAnswer() }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title)
                        .foregroundStyle(Theme.accent)
                }
                .disabled(
                    model.answerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || model.isBusy
                )
                .accessibilityLabel("Send answer to the concierge")
            }
            if model.isBusy {
                Label("The concierge is updating your assignment…", systemImage: "sparkles")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 12))
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
                CandidateCard(match: match, api: api) { decision in
                    Task { await model.decide(match: match, decision: decision) }
                }
            }
        }
    }
}

/// Small badge marking a value the AI estimated from market data.
struct EstimateBadge: View {
    var body: some View {
        Text("AI estimate")
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Theme.accentSoft, in: .capsule)
            .foregroundStyle(Theme.accent)
    }
}

struct CandidateCard: View {
    let match: Match
    let api: APIClient
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

            NavigationLink {
                InterviewView(api: api, matchId: match.id, viewer: .company)
            } label: {
                Label("AI interview", systemImage: "sparkles")
                    .font(.subheadline.weight(.medium))
            }

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
