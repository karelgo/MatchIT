import SwiftUI

struct InterviewView: View {
    @State private var model: InterviewViewModel

    init(api: APIClient, matchId: UUID, viewer: InterviewViewModel.Viewer) {
        _model = State(initialValue: InterviewViewModel(api: api, matchId: matchId, viewer: viewer))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let message = model.errorMessage {
                    ErrorBanner(message: message)
                }
                if model.isLoading {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                } else if let interview = model.interview {
                    progress(interview)
                    if let assessment = interview.assessment {
                        result(assessment)
                        transcript(interview)
                    } else if model.viewer == .specialist, let question = interview.currentQuestion {
                        questionCard(question, interview: interview)
                    } else {
                        waiting(interview)
                    }
                } else {
                    notStarted
                }
            }
            .padding(Theme.screenPadding)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("AI Interview")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
    }

    private var notStarted: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("No interview yet", systemImage: "sparkles")
                .font(.system(.title3, design: .rounded, weight: .semibold))
            Text(
                model.viewer == .company
                    ? "The AI reads the assignment and this specialist's profile, then interviews them on exactly what the profile leaves unproven."
                    : "The AI will ask a few questions about your experience. Answer in your own words — there is no time limit."
            )
            .font(.subheadline)
            .foregroundStyle(.secondary)
            Button {
                Task { await model.start() }
            } label: {
                if model.isSubmitting { ProgressView().tint(.white) } else { Text("Start AI interview") }
            }
            .buttonStyle(.primary)
            .disabled(model.isSubmitting)
        }
        .padding()
        .cardStyle()
    }

    private func progress(_ interview: Interview) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(
                    interview.isComplete
                        ? "Interview complete"
                        : "Question \(min(interview.answeredCount + 1, interview.totalQuestions)) of \(interview.totalQuestions)"
                )
                .font(.system(.subheadline, design: .rounded, weight: .semibold))
                Spacer()
                if interview.isComplete {
                    Image(systemName: "checkmark.seal.fill").foregroundStyle(Theme.success)
                }
            }
            ProgressView(value: interview.progress)
                .tint(Theme.accent)
            Text(interview.gapSummary)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .cardStyle()
    }

    private func questionCard(_ question: InterviewQuestion, interview: Interview) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            TagChip(text: question.skill.capitalized, prominent: true)
            Text(question.question)
                .font(.system(.title3, design: .rounded, weight: .semibold))
            Text(question.rationale)
                .font(.caption)
                .foregroundStyle(.secondary)
            TextEditor(text: $model.draft)
                .frame(minHeight: 150)
                .padding(8)
                .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 12))
                .accessibilityLabel("Your answer")
            Button {
                Task { await model.submitAnswer() }
            } label: {
                if model.isSubmitting {
                    ProgressView().tint(.white)
                } else {
                    Text(interview.answeredCount + 1 == interview.totalQuestions ? "Finish interview" : "Next question")
                }
            }
            .buttonStyle(.primary)
            .disabled(!model.canSubmit)
        }
        .padding()
        .cardStyle()
    }

    private func waiting(_ interview: Interview) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Waiting on the specialist", systemImage: "hourglass")
                .font(.headline)
            Text(
                "\(interview.answeredCount) of \(interview.totalQuestions) questions answered. You'll see the assessment as soon as the interview finishes."
            )
            .font(.subheadline)
            .foregroundStyle(.secondary)
            ForEach(interview.questions, id: \.question) { question in
                Label(question.question, systemImage: "questionmark.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .cardStyle()
    }

    private func result(_ assessment: InterviewAssessment) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 14) {
                ScoreRing(score: assessment.overallScore).frame(width: 58, height: 58)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Interview score")
                        .font(.system(.headline, design: .rounded))
                    if let recommendation = assessment.recommendation {
                        Text(recommendationLabel(recommendation))
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(recommendationColor(recommendation))
                    }
                }
                Spacer()
            }

            if let summary = assessment.summary {
                Text(summary).font(.subheadline)
            }

            bulletList("Strengths", assessment.strengths, systemImage: "checkmark.circle.fill", tint: Theme.success)
            bulletList(
                model.viewer == .company ? "Development areas" : "Where to grow",
                assessment.developmentAreas,
                systemImage: "arrow.up.forward.circle.fill",
                tint: Theme.accent
            )
            if let concerns = assessment.concerns, !concerns.isEmpty {
                bulletList("Concerns", concerns, systemImage: "exclamationmark.triangle.fill", tint: Theme.danger)
            }

            if let perQuestion = assessment.perQuestion, !perQuestion.isEmpty {
                Divider()
                Text("Per question").font(.subheadline.weight(.semibold))
                ForEach(perQuestion, id: \.question) { score in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack {
                            Text(score.question).font(.caption.weight(.medium))
                            Spacer()
                            Text(score.score, format: .percent.precision(.fractionLength(0)))
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                        Text(score.reasoning).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding()
        .cardStyle()
    }

    private func transcript(_ interview: Interview) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Transcript").font(.subheadline.weight(.semibold))
            ForEach(interview.transcript, id: \.question) { entry in
                VStack(alignment: .leading, spacing: 4) {
                    Text(entry.question).font(.caption.weight(.semibold))
                    Text(entry.answer).font(.caption).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 10))
            }
        }
        .padding()
        .cardStyle()
    }

    private func bulletList(
        _ title: String, _ items: [String], systemImage: String, tint: Color
    ) -> some View {
        Group {
            if !items.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    Text(title).font(.subheadline.weight(.semibold))
                    ForEach(items, id: \.self) { item in
                        Label(item, systemImage: systemImage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .labelStyle(.titleAndIcon)
                            .tint(tint)
                    }
                }
            }
        }
    }

    private func recommendationLabel(_ raw: String) -> String {
        switch raw {
        case "strong_yes": "Strong yes"
        case "yes": "Yes"
        case "maybe": "Maybe"
        default: "No"
        }
    }

    private func recommendationColor(_ raw: String) -> Color {
        switch raw {
        case "strong_yes", "yes": Theme.success
        case "maybe": .orange
        default: Theme.danger
        }
    }
}
