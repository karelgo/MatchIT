import Observation
import SwiftUI

@MainActor
@Observable
final class MatchFeedbackViewModel {
    var feedback: MatchFeedback?
    var isLoading = false
    var notYetAvailable = false
    var errorMessage: String?

    private let api: APIClient
    private let matchId: UUID

    init(api: APIClient, matchId: UUID) {
        self.api = api
        self.matchId = matchId
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            feedback = try await api.matchFeedback(matchId: matchId)
            notYetAvailable = feedback == nil
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Why a match went the way it did — the screen every other platform replaces with
/// silence. Everything here is derived from the score the company actually saw.
struct MatchFeedbackView: View {
    @State private var model: MatchFeedbackViewModel
    let matchId: UUID
    private let api: APIClient

    init(api: APIClient, matchId: UUID) {
        self.api = api
        self.matchId = matchId
        _model = State(initialValue: MatchFeedbackViewModel(api: api, matchId: matchId))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let message = model.errorMessage {
                    ErrorBanner(message: message, onRetry: { Task { await model.load() } })
                }
                if model.isLoading {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                } else if model.notYetAvailable {
                    pending
                } else if let feedback = model.feedback {
                    outcome(feedback)
                    if !feedback.costYouMost.isEmpty {
                        factors(
                            "What cost you the most",
                            feedback.costYouMost,
                            footer: feedback.note
                        )
                    }
                    if !feedback.workedInYourFavour.isEmpty {
                        factors("What worked in your favour", feedback.workedInYourFavour)
                    }
                    if feedback.interviewScore != nil {
                        interview(feedback)
                    }
                    NavigationLink {
                        TransparencyReportView(api: api, matchId: matchId)
                    } label: {
                        Label("See the full decision record", systemImage: "doc.text.magnifyingglass")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding()
                            .cardStyle()
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(Theme.screenPadding)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Your feedback")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
    }

    private var pending: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Still open", systemImage: "hourglass")
                .font(.system(.title3, design: .rounded, weight: .semibold))
            Text("The company hasn't decided yet. You'll get the full breakdown either way.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding()
        .cardStyle()
    }

    private func outcome(_ feedback: MatchFeedback) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 14) {
                ScoreRing(score: feedback.totalScore, centerText: "#\(feedback.rank)")
                VStack(alignment: .leading, spacing: 3) {
                    Text(feedback.headline)
                        .font(.system(.headline, design: .rounded))
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Ranked \(feedback.rank) of \(feedback.candidatesScored) considered")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
        }
        .padding()
        .cardStyle()
    }

    private func factors(
        _ title: String, _ factors: [FeedbackFactor], footer: String? = nil
    ) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title).font(.system(.headline, design: .rounded))
            ForEach(factors) { factor in
                VStack(alignment: .leading, spacing: 6) {
                    LevelBar(
                        label: factor.component.capitalized,
                        value: factor.score,
                        trailing: "\(Int(factor.weight * 100))% weight",
                        accessibilityValue: "\(Int(factor.score * 100)) percent"
                    )
                    Text(factor.whatHappened).font(.caption)
                    if let help = factor.whatWouldHelp {
                        Label(help, systemImage: "lightbulb")
                            .font(.caption)
                            .foregroundStyle(Theme.accent)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 10))
            }
            if let footer {
                Text(footer).font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .padding()
        .cardStyle()
    }

    private func interview(_ feedback: MatchFeedback) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("From your interview").font(.system(.headline, design: .rounded))
                Spacer()
                if let score = feedback.interviewScore {
                    Text(score, format: .percent.precision(.fractionLength(0)))
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
            ForEach(feedback.interviewStrengths, id: \.self) { item in
                Label(item, systemImage: "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .tint(Theme.success)
            }
            ForEach(feedback.interviewDevelopmentAreas, id: \.self) { item in
                Label(item, systemImage: "arrow.up.forward.circle.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .tint(Theme.accent)
            }
        }
        .padding()
        .cardStyle()
    }
}
