import ActivityKit
import Foundation

/// Live Activity state for an in-progress AI interview. Compiled into both the
/// app (which starts and updates the activity) and the widget extension (which
/// renders it) — the types must match exactly, so there is one definition.
struct InterviewActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var answeredCount: Int
        var totalQuestions: Int
        var currentSkill: String

        var progress: Double {
            totalQuestions == 0 ? 0 : Double(answeredCount) / Double(totalQuestions)
        }
    }

    /// Fixed for the activity's lifetime.
    var title: String
}
