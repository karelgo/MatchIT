import Foundation
import Observation

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
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func decideTopCard(_ decision: MatchDecision) async {
        guard let top = deck.first else { return }
        deck.removeFirst()
        do {
            let updated = try await api.decide(matchId: top.id, decision: decision)
            if updated.status == "mutual" {
                lastMutualMatch = updated
            }
        } catch {
            errorMessage = error.localizedDescription
            deck.insert(top, at: 0)
        }
    }
}
