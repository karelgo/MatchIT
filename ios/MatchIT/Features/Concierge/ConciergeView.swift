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
                    switch model.phase {
                    case .needsCompanyProfile: companyForm
                    case .describing: describeCard
                    case let .reviewing(assignment): reviewCard(assignment)
                    case let .matched(_, matches): matchList(matches)
                    }
                }
                .padding(Theme.screenPadding)
            }
            // The floating tab bar overlaps the last control in a scroll view otherwise.
            .contentMargins(.bottom, 72, for: .scrollContent)
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Concierge")
            .task { await model.bootstrap() }
        }
    }

    /// Failures are shown beside the action that failed. At the top of a long scroll view
    /// they render off-screen, so a failed request looks like nothing happening at all.
    @ViewBuilder
    private var errorBanner: some View {
        if let message = model.errorMessage {
            ErrorBanner(
                message: message,
                onRetry: model.canRetry ? { Task { await model.retryLastFailure() } } : nil,
                onDismiss: { model.dismissError() }
            )
        }
    }

    @ViewBuilder
    private var activityNote: some View {
        if let activity = model.activity {
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text(activity.message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .combine)
        }
    }

    private var companyForm: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("First, tell us who's hiring")
                .font(.system(.title3, design: .rounded, weight: .semibold))
            TextField("Company name", text: $model.companyName)
            TextField("Industry (optional)", text: $model.companyIndustry)
            errorBanner
            activityNote
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
            ZStack(alignment: .bottomTrailing) {
                TextEditor(text: $model.problemText)
                    .frame(minHeight: 160)
                    .padding(8)
                    .background(Theme.nestedSurface, in: .rect(cornerRadius: 12))
                    // Autocorrect rewrites technical English on a non-English keyboard —
                    // "observability" became "observatiepost" — and the AI then extracts
                    // requirements from corrupted input.
                    .autocorrectionDisabled()
                    .accessibilityLabel("Problem description")
                Button {
                    model.toggleDictation()
                } label: {
                    Image(
                        systemName: model.transcriber.isRecording
                            ? "stop.circle.fill" : "mic.circle.fill"
                    )
                    .font(.system(size: 30))
                    .foregroundStyle(model.transcriber.isRecording ? Theme.danger : Theme.accent)
                    .symbolEffect(.pulse, isActive: model.transcriber.isRecording)
                }
                .padding(10)
                .accessibilityLabel(
                    model.transcriber.isRecording ? "Stop dictation" : "Dictate your problem"
                )
            }
            if model.transcriber.isRecording {
                Label("Listening — talk like you'd talk to a colleague", systemImage: "waveform")
                    .font(.caption)
                    .foregroundStyle(Theme.accent)
            }
            if let speechError = model.transcriber.errorMessage {
                Text(speechError).font(.caption).foregroundStyle(Theme.danger)
            }

            // Replaces the static example line: same Fabric example, but tappable, and
            // only offered while there is nothing to lose by filling the field.
            if model.problemText.isEmpty {
                examplePrompts
            }
            if let hint = model.descriptionHint {
                Text(hint)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            errorBanner
            activityNote
            Button {
                Task { await model.submitProblem() }
            } label: {
                Label("Let AI write the assignment", systemImage: "sparkles")
                    .labelStyle(.titleOnly)
            }
            .buttonStyle(.primary)
            .disabled(!model.canSubmitDescription || model.isBusy)
        }
        .padding()
        .cardStyle()
    }

    private var examplePrompts: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Or start from an example")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach(ConciergeViewModel.examplePrompts, id: \.self) { prompt in
                Button {
                    model.use(examplePrompt: prompt)
                } label: {
                    Text(prompt)
                        .font(.caption)
                        .multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(Theme.accentSoft, in: .rect(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .accessibilityHint("Fills the description with this example")
            }
        }
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
                    ChipFlow(items: role.mustHaveSkills.map(SkillName.display))
                    if !role.niceToHaveSkills.isEmpty {
                        ChipFlow(items: role.niceToHaveSkills.map { "+ \(SkillName.display($0))" })
                    }
                }
                .padding(12)
                .background(Theme.accentSoft, in: .rect(cornerRadius: 12))
            }

            estimateRows(assignment.requirements)

            IntakeTranscriptView(history: priorHistory(assignment))

            conciergeThread(assignment)

            errorBanner
            activityNote
            Button {
                Task { await model.findSpecialists() }
            } label: {
                Text("Find specialists")
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

    /// Everything before the live question set. The newest concierge turn *is* the list
    /// rendered underneath, so including it in the transcript says the same thing twice.
    private func priorHistory(_ assignment: Assignment) -> [IntakeMessage] {
        guard !assignment.requirements.clarifyingQuestions.isEmpty,
              assignment.intakeHistory.last?.isCompany == false
        else { return assignment.intakeHistory }
        return assignment.intakeHistory.dropLast()
    }

    /// The concierge conversation. The input stays available even when the AI has no
    /// further questions — otherwise the model alone decides when the conversation is
    /// over, and there is no way to volunteer a correction it did not ask for.
    private func conciergeThread(_ assignment: Assignment) -> some View {
        let questions = assignment.requirements.clarifyingQuestions
        return VStack(alignment: .leading, spacing: 10) {
            if questions.isEmpty {
                Label("The concierge has everything it needs", systemImage: "checkmark.seal")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.success)
                Text("Anything to add or correct?")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Text("The concierge would like to know:")
                    .font(.subheadline.weight(.semibold))
                ForEach(questions, id: \.self) { question in
                    Label(question, systemImage: "questionmark.circle")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 8) {
                TextField(
                    questions.isEmpty ? "Add or correct anything…" : "Answer in your own words…",
                    text: $model.answerText,
                    axis: .vertical
                )
                .lineLimit(1 ... 4)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                Button {
                    Task { await model.sendAnswer() }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                        // Below 44pt this is under the minimum comfortable tap target.
                        .frame(width: 44, height: 44)
                        .foregroundStyle(Theme.accent)
                        .contentShape(.rect)
                }
                .disabled(
                    model.answerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || model.isBusy
                )
                .accessibilityLabel("Send to the concierge")
            }
        }
        .padding(12)
        .background(Theme.nestedSurface, in: .rect(cornerRadius: 12))
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
            if case let .matched(assignment, _) = model.phase,
               assignment.requirements.roles.contains(where: { $0.count > 1 })
                   || assignment.requirements.roles.count > 1 {
                NavigationLink {
                    TeamView(api: api, assignmentId: assignment.id)
                } label: {
                    Label("Build a team instead", systemImage: "person.3.fill")
                        .font(.subheadline.weight(.medium))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(Theme.accentSoft, in: .rect(cornerRadius: 12))
                }
            }
            errorBanner
            if matches.isEmpty {
                ContentUnavailableView(
                    "No specialists yet",
                    systemImage: "person.2.slash",
                    description: Text("As specialists join, matches will appear here instantly.")
                )
            }
            ForEach(Array(matches.enumerated()), id: \.element.id) { index, match in
                CandidateCard(match: match, api: api, rank: index + 1) { decision in
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
    let rank: Int
    let onDecision: (MatchDecision) -> Void

    @State private var showsBreakdown = false
    @State private var showsDetail = false

    private var quality: MatchQuality { MatchQuality(score: match.score) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                showsDetail = true
            } label: {
                summary
            }
            .buttonStyle(.plain)
            .accessibilityHint("Opens the full candidate profile")

            NavigationLink {
                InterviewView(api: api, matchId: match.id, viewer: .company)
            } label: {
                Label("AI interview", systemImage: "sparkles")
                    .font(.subheadline.weight(.medium))
            }

            // Offered once a decision exists: the signed record of how this
            // candidacy was handled, which is the document you want on file long
            // before anyone asks how the shortlist was produced.
            if match.companyDecision != .pending {
                NavigationLink {
                    TransparencyReportView(api: api, matchId: match.id)
                } label: {
                    Label("Decision record", systemImage: "doc.text.magnifyingglass")
                        .font(.subheadline.weight(.medium))
                }
            }

            ChipFlow(items: match.specialist.skills.prefix(6).map { SkillName.display($0.name) })

            Button {
                withAnimation(.easeInOut(duration: 0.2)) { showsBreakdown.toggle() }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "chart.bar.xaxis")
                    Text(showsBreakdown ? "Hide why" : "Why this match")
                    Image(systemName: "chevron.down")
                        .rotationEffect(.degrees(showsBreakdown ? 0 : -90))
                        .font(.caption2.weight(.semibold))
                }
                .font(.footnote.weight(.medium))
            }
            .buttonStyle(.plain)

            if showsBreakdown {
                MatchBreakdownView(breakdown: match.breakdown)
            }

            decisionControls
        }
        .padding()
        .cardStyle()
        .sheet(isPresented: $showsDetail) {
            SpecialistDetailSheet(match: match, onDecision: onDecision)
        }
    }

    private var summary: some View {
        HStack(alignment: .top, spacing: 12) {
            ScoreRing(score: match.score, centerText: "#\(rank)")
            VStack(alignment: .leading, spacing: 4) {
                Text(match.specialist.headline)
                    .font(.headline)
                    .frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 6) {
                    MatchQualityBadge(quality: quality)
                    if rank == 1 {
                        Text("Best match")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(.secondary)
                    }
                }
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
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            """
            Rank \(rank), \(quality.label). \(match.specialist.headline). \
            \(match.specialist.yearsExperience) years, \(match.specialist.country), \
            \(match.specialist.remotePreference.displayName)
            """
        )
    }

    @ViewBuilder
    private var decisionControls: some View {
        if match.status == "mutual" {
            // Chat really is unlocked here, so the claim stands — but it lives in the
            // Messages tab, and a promise the user cannot act on from this card is only
            // marginally better than one that isn't true.
            VStack(alignment: .leading, spacing: 4) {
                Label("It's a match — you both accepted", systemImage: "checkmark.seal.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.success)
                Text("Chat is open under Messages.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .combine)
            NavigationLink {
                ContractView(api: api, matchId: match.id, isCompany: true)
            } label: {
                Label("Contract", systemImage: "doc.text")
                    .font(.subheadline.weight(.medium))
            }
        } else if match.companyDecision == .pending {
            HStack(spacing: 10) {
                Button {
                    onDecision(.rejected)
                } label: {
                    Label("Pass", systemImage: "xmark").frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                Button {
                    onDecision(.accepted)
                } label: {
                    Label("Shortlist", systemImage: "checkmark").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.accent)
            }
            .controlSize(.large)
        } else {
            Text(
                match.companyDecision == .accepted
                    ? "Shortlisted — waiting for the specialist"
                    : "Passed"
            )
            .font(.subheadline)
            .foregroundStyle(.secondary)
        }
    }
}
