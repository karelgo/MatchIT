import ActivityKit
import Foundation

/// Drives the interview Live Activity from the interview screen.
///
/// Everything here is best-effort: Live Activities can be disabled system-wide
/// or per-app, and a missing island must never affect the interview itself.
@MainActor
final class InterviewActivityController {
    private var activity: Activity<InterviewActivityAttributes>?

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
        Task { await activity.update(ActivityContent(state: state, staleDate: nil)) }
    }

    func end(answered: Int, total: Int) {
        guard let activity else { return }
        let state = InterviewActivityAttributes.ContentState(
            answeredCount: answered, totalQuestions: total, currentSkill: "Complete"
        )
        Task {
            await activity.end(
                ActivityContent(state: state, staleDate: nil), dismissalPolicy: .default
            )
        }
        self.activity = nil
    }
}
