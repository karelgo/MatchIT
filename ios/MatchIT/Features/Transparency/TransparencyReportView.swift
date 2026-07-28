import Observation
import SwiftUI

@MainActor
@Observable
final class TransparencyReportViewModel {
    var report: TransparencyReport?
    var isLoading = false
    /// Distinguished from an error: before the company decides there is nothing to
    /// report, which is a state to explain rather than a failure to apologise for.
    var notYetAvailable = false
    var errorMessage: String?

    private let api: APIClient
    private let matchId: UUID

    init(api: APIClient, matchId: UUID) {
        self.api = api
        self.matchId = matchId
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            report = try await api.transparencyReport(matchId: matchId)
            notYetAvailable = report == nil
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// The signed record of one hiring decision, shown identically to both parties.
struct TransparencyReportView: View {
    @State private var model: TransparencyReportViewModel

    init(api: APIClient, matchId: UUID) {
        _model = State(initialValue: TransparencyReportViewModel(api: api, matchId: matchId))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let message = model.errorMessage {
                    ErrorBanner(message: message, onRetry: { Task { await model.load() } })
                }
                if model.isLoading {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                } else if model.notYetAvailable {
                    pending
                } else if let body = model.report?.report {
                    header(body)
                    ranking(body.ranking)
                    if let explanation = body.interview { interview(explanation) }
                    decisions(body.decisions)
                    oversight(body)
                    signature(body.signature, markdown: model.report?.markdown ?? "")
                }
            }
            .padding(Theme.screenPadding)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("How this was decided")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
    }

    private var pending: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Not decided yet", systemImage: "hourglass")
                .font(.system(.title3, design: .rounded, weight: .semibold))
            Text(
                "The report is issued once a decision has been made. It will show exactly how you were scored, what the interview asked and why, and who decided what."
            )
            .font(.subheadline)
            .foregroundStyle(.secondary)
        }
        .padding()
        .cardStyle()
    }

    private func header(_ body: TransparencyReportBody) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(body.engagement.assignmentSummary)
                .font(.system(.headline, design: .rounded))
            Text("\(body.engagement.company) · \(body.engagement.specialistReference)")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(body.statement)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding()
        .cardStyle()
    }

    private func ranking(_ ranking: RankingExplanation) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 14) {
                ScoreRing(score: ranking.totalScore, centerText: "#\(ranking.rank)")
                VStack(alignment: .leading, spacing: 2) {
                    Text("Ranked \(ranking.rank) of \(ranking.candidatesScored)")
                        .font(.system(.headline, design: .rounded))
                    Text(ranking.totalScore, format: .percent.precision(.fractionLength(0)))
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            Text(ranking.method).font(.caption).foregroundStyle(.secondary)

            ForEach(ranking.components) { component in
                LevelBar(
                    label: component.component.capitalized,
                    value: component.score,
                    trailing: "\(Int(component.weight * 100))% weight",
                    accessibilityValue:
                        "\(Int(component.score * 100)) percent, weighted \(Int(component.weight * 100)) percent",
                    footnote: component.howItIsMeasured
                )
            }
            Text("Ranking definition \(ranking.definitionFingerprint)")
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)
        }
        .padding()
        .cardStyle()
    }

    private func interview(_ interview: InterviewExplanation) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Interview").font(.system(.headline, design: .rounded))
            Text(interview.scoredOn).font(.caption).foregroundStyle(.secondary)
            Text(interview.gapSummary).font(.subheadline)

            ForEach(interview.questions) { question in
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        TagChip(text: question.skill.capitalized)
                        Spacer()
                        if let score = question.score {
                            Text(score, format: .percent.precision(.fractionLength(0)))
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                        if question.answerInputMode == "voice" {
                            Image(systemName: "waveform")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                                .accessibilityLabel("Answered by voice")
                        }
                    }
                    Text(question.question).font(.subheadline.weight(.medium))
                    Text("Asked because: \(question.askedBecause)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let reasoning = question.reasoning {
                        Text(reasoning).font(.caption2).foregroundStyle(.tertiary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 10))
            }

            if let recommendation = interview.recommendation {
                Text("Recommendation to the hiring manager: \(recommendation.replacingOccurrences(of: "_", with: " "))")
                    .font(.subheadline.weight(.semibold))
            }
            bullets("Strengths", interview.strengths, tint: Theme.success)
            bullets("Development areas", interview.developmentAreas, tint: Theme.accent)
            bullets("Concerns raised", interview.concerns, tint: Theme.danger)
        }
        .padding()
        .cardStyle()
    }

    private func decisions(_ decisions: [ReportedDecision]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Decisions").font(.system(.headline, design: .rounded))
            ForEach(decisions) { decision in
                HStack(alignment: .firstTextBaseline) {
                    Text(decision.party.capitalized).font(.subheadline.weight(.medium))
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(decision.decision.replacingOccurrences(of: "_", with: " "))
                            .font(.subheadline)
                        if let madeBy = decision.madeBy {
                            Text(madeBy).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
                .accessibilityElement(children: .combine)
            }
        }
        .padding()
        .cardStyle()
    }

    private func oversight(_ body: TransparencyReportBody) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Human oversight").font(.system(.headline, design: .rounded))
            Text(body.humanOversight).font(.footnote).foregroundStyle(.secondary)
            Divider()
            Text("Your rights").font(.subheadline.weight(.semibold))
            ForEach(body.yourRights, id: \.self) { right in
                Label(right, systemImage: "checkmark.shield")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Divider()
            Text("AI systems involved").font(.subheadline.weight(.semibold))
            ForEach(body.aiSystems) { system in
                HStack {
                    Text(system.name).font(.caption)
                    Spacer()
                    Text(system.definitionFingerprint)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding()
        .cardStyle()
    }

    private func signature(_ signature: ReportSignature, markdown: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Signed with \(signature.algorithm)", systemImage: "checkmark.seal.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Theme.success)
            Text(signature.value)
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)
                .textSelection(.enabled)
            Text(
                "Anyone you send this to can confirm it is unaltered, without a MatchIT account."
            )
            .font(.caption)
            .foregroundStyle(.secondary)
            ShareLink(item: markdown) {
                Label("Share the full report", systemImage: "square.and.arrow.up")
            }
            .font(.subheadline.weight(.semibold))
        }
        .padding()
        .cardStyle()
    }

    private func bullets(_ title: String, _ items: [String], tint: Color) -> some View {
        Group {
            if !items.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title).font(.subheadline.weight(.semibold))
                    ForEach(items, id: \.self) { item in
                        Label(item, systemImage: "circle.fill")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .tint(tint)
                    }
                }
            }
        }
    }
}
