import Foundation
import Observation

/// Company-side flow: describe the problem, review the AI-written assignment,
/// then let the engine propose ranked specialists.
@MainActor
@Observable
final class ConciergeViewModel {
    enum Phase: Equatable {
        case needsCompanyProfile
        case describing
        case reviewing(Assignment)
        case matched(Assignment, [Match])
    }

    var phase: Phase = .describing
    var problemText = ""
    var answerText = ""
    var companyName = ""
    var companyIndustry = ""
    var isBusy = false
    var errorMessage: String?

    let transcriber = SpeechTranscriber()
    private var dictationBase = ""

    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    var canSubmitDescription: Bool {
        problemText.trimmingCharacters(in: .whitespacesAndNewlines).count >= 20
    }

    func bootstrap() async {
        do {
            if try await api.myCompanyProfile() == nil {
                phase = .needsCompanyProfile
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveCompanyProfile() async {
        guard !companyName.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        await run {
            _ = try await self.api.upsertCompanyProfile(
                name: self.companyName, industry: self.companyIndustry, country: "NL"
            )
            self.phase = .describing
        }
    }

    func submitProblem() async {
        await run {
            let assignment = try await self.api.createAssignment(description: self.problemText)
            self.phase = .reviewing(assignment)
        }
    }

    func sendAnswer() async {
        guard case let .reviewing(assignment) = phase else { return }
        let answer = answerText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !answer.isEmpty else { return }
        await run {
            let updated = try await self.api.refineAssignment(
                assignmentId: assignment.id, answer: answer
            )
            self.answerText = ""
            self.phase = .reviewing(updated)
        }
    }

    func findSpecialists() async {
        guard case let .reviewing(assignment) = phase else { return }
        await run {
            let matches = try await self.api.generateMatches(assignmentId: assignment.id)
            self.phase = .matched(assignment, matches)
        }
    }

    func decide(match: Match, decision: MatchDecision) async {
        guard case let .matched(assignment, matches) = phase else { return }
        await run {
            let updated = try await self.api.decide(matchId: match.id, decision: decision)
            let refreshed = matches.map { $0.id == updated.id ? updated : $0 }
            self.phase = .matched(assignment, refreshed)
        }
    }

    func startOver() {
        problemText = ""
        answerText = ""
        phase = .describing
    }

    /// Voice-first intake: dictation streams into the problem description,
    /// appending to whatever was already typed.
    func toggleDictation() {
        if transcriber.isRecording {
            transcriber.stop()
            return
        }
        let existing = problemText.trimmingCharacters(in: .whitespacesAndNewlines)
        dictationBase = existing.isEmpty ? "" : existing + " "
        transcriber.start { [weak self] transcript in
            guard let self else { return }
            self.problemText = self.dictationBase + transcript
        }
    }

    private func run(_ work: @escaping @MainActor () async throws -> Void) async {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            try await work()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
