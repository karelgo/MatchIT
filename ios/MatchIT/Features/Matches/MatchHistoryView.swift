import Observation
import SwiftUI

@MainActor
@Observable
final class MatchHistoryViewModel {
    var matches: [Match] = []
    var isLoading = false
    var errorMessage: String?

    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            matches = try await api.matchHistory()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Everything that closed, with the reason attached to each one.
///
/// This screen exists because the alternative is silence, and silence is the single
/// most common complaint specialists have about every platform in this market. The
/// answer already exists — the score breakdown was computed when the match was made —
/// so not showing it would be a choice.
struct MatchHistoryView: View {
    @State private var model: MatchHistoryViewModel
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
        _model = State(initialValue: MatchHistoryViewModel(api: api))
    }

    var body: some View {
        Group {
            if let message = model.errorMessage {
                ErrorBanner(message: message, onRetry: { Task { await model.load() } })
                    .padding(Theme.screenPadding)
            } else if model.isLoading, model.matches.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if model.matches.isEmpty {
                ContentUnavailableView(
                    "Nothing closed yet",
                    systemImage: "clock.arrow.circlepath",
                    description: Text(
                        "Once an opportunity is decided either way, it appears here with the full reason."
                    )
                )
            } else {
                List(model.matches) { match in
                    NavigationLink {
                        MatchFeedbackView(api: api, matchId: match.id)
                    } label: {
                        row(match)
                    }
                }
                .listStyle(.insetGrouped)
            }
        }
        .navigationTitle("Past opportunities")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .refreshable { await model.load() }
    }

    private func row(_ match: Match) -> some View {
        HStack(spacing: 12) {
            ScoreRing(score: match.score)
            VStack(alignment: .leading, spacing: 3) {
                Text(match.assignment.requirements.roles.first?.title ?? "Assignment")
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
                Text(outcome(match))
                    .font(.caption)
                    .foregroundStyle(tint(match))
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func outcome(_ match: Match) -> String {
        if match.specialistDecision == .rejected { return "You declined" }
        if match.companyDecision == .rejected { return "Not selected" }
        if match.status == "mutual" { return "Matched" }
        return "Waiting on you"
    }

    private func tint(_ match: Match) -> Color {
        if match.status == "mutual" { return Theme.success }
        if match.companyDecision == .rejected { return .secondary }
        return .secondary
    }
}
