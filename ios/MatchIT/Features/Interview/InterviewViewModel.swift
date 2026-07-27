import Foundation
import Observation

/// One AI screening interview. The same screen serves both sides — the backend
/// projects the assessment, so the specialist simply never receives the hiring
/// manager's risks or recommendation.
@MainActor
@Observable
final class InterviewViewModel {
    enum Viewer {
        case specialist
        case company
    }

    let matchId: UUID
    let viewer: Viewer

    var interview: Interview?
    var draft = ""
    var isLoading = false
    var isSubmitting = false
    var errorMessage: String?

    private let api: APIClient
    private let liveActivity = InterviewActivityController()

    init(api: APIClient, matchId: UUID, viewer: Viewer) {
        self.api = api
        self.matchId = matchId
        self.viewer = viewer
    }

    var canSubmit: Bool {
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSubmitting
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            interview = try await api.interview(matchId: matchId)
            errorMessage = nil
            syncLiveActivity()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// The Live Activity mirrors the specialist's in-progress interview; the
    /// company never gets one, and a finished interview ends it.
    private func syncLiveActivity() {
        guard viewer == .specialist, let interview else { return }
        if interview.isComplete {
            liveActivity.end(answered: interview.answeredCount, total: interview.totalQuestions)
        } else if let question = interview.currentQuestion {
            liveActivity.start(
                title: "AI screening interview",
                answered: interview.answeredCount,
                total: interview.totalQuestions,
                skill: question.skill
            )
            liveActivity.update(
                answered: interview.answeredCount,
                total: interview.totalQuestions,
                skill: question.skill
            )
        }
    }

    func start() async {
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            interview = try await api.startInterview(matchId: matchId)
            errorMessage = nil
            syncLiveActivity()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func submitAnswer() async {
        let answer = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !answer.isEmpty else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            interview = try await api.answerInterview(matchId: matchId, answer: answer)
            draft = ""
            errorMessage = nil
            syncLiveActivity()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
