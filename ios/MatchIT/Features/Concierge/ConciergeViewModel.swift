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

    /// What the AI is doing right now. Extraction against a hosted model takes tens of
    /// seconds, which is far too long to represent as an unlabelled spinner.
    enum Activity {
        case savingProfile
        case extracting
        case refining
        case matching

        var message: String {
            switch self {
            case .savingProfile: "Saving your company profile…"
            case .extracting: "Reading your problem and drafting the assignment…"
            case .refining: "Updating your assignment with your answer…"
            case .matching: "Ranking specialists against your assignment…"
            }
        }
    }

    /// Recorded so a failure can offer Retry instead of making the user retype.
    private enum Retryable {
        case saveCompanyProfile
        case submitProblem
        case sendAnswer
        case findSpecialists
    }

    /// Starting points for people who freeze at an empty box — by far the cheapest
    /// improvement to first-run completion.
    static let examplePrompts = [
        "Our checkout falls over during peak traffic and we only find out from customer complaints. We need someone senior on observability and scaling.",
        "We need two Microsoft Fabric architects to migrate our on-prem data warehouse within six months.",
        "Our iOS app ships too slowly and has no test coverage. Looking for a senior SwiftUI engineer to lead a rebuild.",
    ]

    var phase: Phase = .describing
    var problemText = ""
    var answerText = ""
    var companyName = ""
    var companyIndustry = ""
    var activity: Activity?
    var errorMessage: String?

    let transcriber = SpeechTranscriber()
    private var dictationBase = ""

    private var lastFailed: Retryable?
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    var isBusy: Bool { activity != nil }

    var canSubmitDescription: Bool {
        problemText.trimmingCharacters(in: .whitespacesAndNewlines).count >= 20
    }

    /// Why the submit button is disabled, so the control is not just inert.
    var descriptionHint: String? {
        let trimmed = problemText.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        let remaining = 20 - trimmed.count
        return remaining > 0 ? "A few more words — \(remaining) to go." : nil
    }

    var canRetry: Bool { lastFailed != nil }

    func use(examplePrompt: String) {
        problemText = examplePrompt
    }

    func dismissError() {
        errorMessage = nil
        lastFailed = nil
    }

    /// Statuses that mean there is nothing left to work on.
    private static let finishedStatuses: Set<String> = ["completed", "cancelled"]

    func bootstrap() async {
        do {
            guard try await api.myCompanyProfile() != nil else {
                phase = .needsCompanyProfile
                return
            }
            // Resume work in progress. Without this, relaunching drops the user back to an
            // empty box even though the assignment exists server-side, and the natural
            // response is to describe the problem again and create a duplicate.
            if let latest = try await api.assignments().first(where: {
                !Self.finishedStatuses.contains($0.status.lowercased())
            }) {
                phase = .reviewing(latest)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveCompanyProfile() async {
        guard !companyName.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        await run(.savingProfile, retryAs: .saveCompanyProfile) {
            _ = try await self.api.upsertCompanyProfile(
                name: self.companyName, industry: self.companyIndustry, country: "NL"
            )
            self.phase = .describing
        }
    }

    func submitProblem() async {
        await run(.extracting, retryAs: .submitProblem) {
            let assignment = try await self.api.createAssignment(description: self.problemText)
            self.phase = .reviewing(assignment)
        }
    }

    func sendAnswer() async {
        guard case let .reviewing(assignment) = phase else { return }
        let answer = answerText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !answer.isEmpty else { return }
        await run(.refining, retryAs: .sendAnswer) {
            let updated = try await self.api.refineAssignment(
                assignmentId: assignment.id, answer: answer
            )
            self.answerText = ""
            self.phase = .reviewing(updated)
        }
    }

    func findSpecialists() async {
        guard case let .reviewing(assignment) = phase else { return }
        await run(.matching, retryAs: .findSpecialists) {
            let matches = try await self.api.generateMatches(assignmentId: assignment.id)
            self.phase = .matched(assignment, matches)
        }
    }

    func decide(match: Match, decision: MatchDecision) async {
        guard case let .matched(assignment, matches) = phase else { return }
        await run(.matching, retryAs: nil) {
            let updated = try await self.api.decide(matchId: match.id, decision: decision)
            let refreshed = matches.map { $0.id == updated.id ? updated : $0 }
            self.phase = .matched(assignment, refreshed)
        }
    }

    func retryLastFailure() async {
        guard let action = lastFailed else { return }
        lastFailed = nil
        switch action {
        case .saveCompanyProfile: await saveCompanyProfile()
        case .submitProblem: await submitProblem()
        case .sendAnswer: await sendAnswer()
        case .findSpecialists: await findSpecialists()
        }
    }

    func startOver() {
        problemText = ""
        answerText = ""
        errorMessage = nil
        lastFailed = nil
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

    private func run(
        _ activity: Activity,
        retryAs retryable: Retryable?,
        _ work: @escaping @MainActor () async throws -> Void
    ) async {
        self.activity = activity
        errorMessage = nil
        lastFailed = nil
        defer { self.activity = nil }
        do {
            try await work()
        } catch {
            errorMessage = error.localizedDescription
            lastFailed = retryable
        }
    }
}
