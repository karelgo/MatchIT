import Foundation
import Observation
import WidgetKit

/// Specialist-side opportunity deck: swipe right to accept, left to pass.
@MainActor
@Observable
final class MatchDeckViewModel {
    /// A decision made but not yet sent, so it can be taken back.
    struct PendingDecision: Identifiable {
        let id = UUID()
        let match: Match
        let decision: MatchDecision

        var summary: String {
            let role = match.assignment.requirements.roles.first?.title ?? "opportunity"
            return decision == .accepted ? "Accepted \(role)" : "Passed on \(role)"
        }
    }

    var deck: [Match] = []
    var isLoading = false
    var errorMessage: String?
    var lastMutualMatch: Match?
    private(set) var pendingUndo: PendingDecision?

    /// Accepting or passing decides a contract worth months of work, so the decision is
    /// held briefly before being sent. That makes undo genuinely free rather than needing
    /// a second write the API cannot express — there is no way to return a match to
    /// pending once decided.
    private let undoWindow: Duration = .seconds(8)
    private var commitTask: Task<Void, Never>?

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

    func decideTopCard(_ decision: MatchDecision) {
        guard let top = deck.first else { return }
        // Only one decision is ever undoable; making another commits the previous one.
        flushPendingDecision()
        deck.removeFirst()
        // The card leaves the deck now, not when the decision is sent, so the widget has
        // to follow the deck rather than the commit — otherwise it stays stale for the
        // whole undo window.
        publishWidgetSnapshot()
        let pending = PendingDecision(match: top, decision: decision)
        pendingUndo = pending
        commitTask = Task { [weak self] in
            try? await Task.sleep(for: self?.undoWindow ?? .seconds(8))
            guard !Task.isCancelled else { return }
            await self?.commit(pending)
        }
    }

    func undo() {
        commitTask?.cancel()
        commitTask = nil
        guard let pending = pendingUndo else { return }
        pendingUndo = nil
        deck.insert(pending.match, at: 0)
        publishWidgetSnapshot()
    }

    /// Send a held decision immediately. Called when leaving the screen so a decision is
    /// never silently dropped by the undo window.
    func flushPendingDecision() {
        guard let pending = pendingUndo else { return }
        commitTask?.cancel()
        commitTask = nil
        pendingUndo = nil
        Task { await commit(pending) }
    }

    private func commit(_ pending: PendingDecision) async {
        if pendingUndo?.id == pending.id { pendingUndo = nil }
        do {
            let updated = try await api.decide(matchId: pending.match.id, decision: pending.decision)
            if updated.status == "mutual" {
                lastMutualMatch = updated
            }
            publishWidgetSnapshot()
        } catch {
            errorMessage = error.localizedDescription
            deck.insert(pending.match, at: 0)
        }
    }
}
