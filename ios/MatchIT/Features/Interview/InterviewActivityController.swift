import ActivityKit
import Foundation

/// Drives the interview Live Activity from the interview screen.
///
/// Everything here is best-effort: Live Activities can be disabled system-wide
/// or per-app, and a missing island must never affect the interview itself.
@MainActor
final class InterviewActivityController {
    private var activity: Activity<InterviewActivityAttributes>?

    /// `Activity` is not `Sendable`, and its `update`/`end` are nonisolated and async, so
    /// handing them a main actor-isolated handle is a cross-isolation send the compiler
    /// rejects. ActivityKit synchronises its own state and the handle is only ever read,
    /// so the hand-off is made explicit here rather than spread across call sites.
    private struct Handoff: @unchecked Sendable {
        let activity: Activity<InterviewActivityAttributes>
    }

    func start(title: String, answered: Int, total: Int, skill: String) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled, activity == nil else { return }
        let state = InterviewActivityAttributes.ContentState(
            answeredCount: answered, totalQuestions: total, currentSkill: skill
        )
        activity = try? Activity.request(
            attributes: InterviewActivityAttributes(title: title),
            content: ActivityContent(state: state, staleDate: nil)
        )
    }

    func update(answered: Int, total: Int, skill: String) {
        guard let activity else { return }
        let state = InterviewActivityAttributes.ContentState(
            answeredCount: answered, totalQuestions: total, currentSkill: skill
        )
        let handoff = Handoff(activity: activity)
        Task { await handoff.activity.update(ActivityContent(state: state, staleDate: nil)) }
    }

    func end(answered: Int, total: Int) {
        guard let activity else { return }
        let state = InterviewActivityAttributes.ContentState(
            answeredCount: answered, totalQuestions: total, currentSkill: "Complete"
        )
        let handoff = Handoff(activity: activity)
        Task {
            await handoff.activity.end(
                ActivityContent(state: state, staleDate: nil), dismissalPolicy: .default
            )
        }
        self.activity = nil
    }
}
