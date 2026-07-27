import Foundation
import Observation
import WidgetKit

/// Specialist-side opportunity deck: swipe right to accept, left to pass.
@MainActor
@Observable
final class MatchDeckViewModel {
    var deck: [Match] = []
    var isLoading = false
    var errorMessage: String?
    var lastMutualMatch: Match?

    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            deck = try await api.opportunityInbox()
            publishWidgetSnapshot()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func publishWidgetSnapshot() {
        SharedStore.save(
            WidgetSnapshot(
                opportunityCount: deck.count,
                topOpportunityTitle: deck.first?.assignment.requirements.roles.first?.title,
                topScore: deck.first?.score,
                updatedAt: .now
            )
        )
        WidgetCenter.shared.reloadTimelines(ofKind: SharedStore.widgetKind)
    }

    func decideTopCard(_ decision: MatchDecision) async {
        guard let top = deck.first else { return }
        deck.removeFirst()
        do {
            let updated = try await api.decide(matchId: top.id, decision: decision)
            if updated.status == "mutual" {
                lastMutualMatch = updated
            }
            publishWidgetSnapshot()
        } catch {
            errorMessage = error.localizedDescription
            deck.insert(top, at: 0)
        }
    }
}
