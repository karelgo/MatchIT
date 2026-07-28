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

    /// Dictation runs on-device, so only the text ever leaves the phone — no
    /// recording is uploaded, stored or analysed. The flag below records that the
    /// answer was spoken purely so the transparency report can say so; content is
    /// what gets scored either way.
    let transcriber = SpeechTranscriber()
    private var dictationBase = ""
    private var answerWasDictated = false

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

    /// Speak the answer instead of typing it. Some people think better out loud, and
    /// typing four paragraphs on a phone is a barrier that has nothing to do with
    /// competence — which is the whole reason voice is here and video is not.
    func toggleDictation() {
        if transcriber.isRecording {
            transcriber.stop()
            return
        }
        let existing = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        dictationBase = existing.isEmpty ? "" : existing + " "
        answerWasDictated = true
        transcriber.start { [weak self] transcript in
            guard let self else { return }
            self.draft = self.dictationBase + transcript
        }
    }

    func submitAnswer() async {
        transcriber.stop()
        let answer = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !answer.isEmpty else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            interview = try await api.answerInterview(
                matchId: matchId,
                answer: answer,
                inputMode: answerWasDictated ? "voice" : "text"
            )
            draft = ""
            answerWasDictated = false
            errorMessage = nil
            syncLiveActivity()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
