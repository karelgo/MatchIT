import SwiftUI

/// Full detail for one opportunity: the score breakdown, and the assignment summary
/// without the truncation the deck card needs to stay a stable size.
struct OpportunityDetailSheet: View {
    let match: Match

    @Environment(\.dismiss) private var dismiss

    private var requirements: AssignmentRequirements { match.assignment.requirements }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(alignment: .leading, spacing: 10) {
                        if let role = requirements.roles.first {
                            Text("\(role.count)× \(role.title) · \(role.seniority.capitalized)")
                                .font(.system(.title3, design: .rounded, weight: .semibold))
                        }
                        MatchQualityBadge(quality: MatchQuality(score: match.score))
                        Text(requirements.summary)
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
                    .cardStyle()

                    MatchBreakdownView(breakdown: match.breakdown)
                        .padding(4)
                        .cardStyle()

                    if let role = requirements.roles.first {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Must have")
                                .font(.subheadline.weight(.semibold))
                            ChipFlow(items: role.mustHaveSkills.map(SkillName.display))
                            if !role.niceToHaveSkills.isEmpty {
                                Text("Nice to have")
                                    .font(.subheadline.weight(.semibold))
                                ChipFlow(items: role.niceToHaveSkills.map(SkillName.display))
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(16)
                        .cardStyle()
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Engagement")
                            .font(.subheadline.weight(.semibold))
                        if let max = requirements.budget.maxHourly {
                            HStack(spacing: 6) {
                                Label(
                                    "Up to \(Int(max)) \(requirements.budget.currency) per hour",
                                    systemImage: "eurosign.circle"
                                )
                                if requirements.budgetIsEstimated { EstimateBadge() }
                            }
                        }
                        if let weeks = requirements.durationWeeks {
                            HStack(spacing: 6) {
                                Label("About \(weeks) weeks", systemImage: "calendar")
                                if requirements.durationIsEstimated { EstimateBadge() }
                            }
                        }
                        Label(
                            requirements.remoteAllowed ? "Remote allowed" : "On-site",
                            systemImage: requirements.remoteAllowed ? "wifi" : "building.2"
                        )
                        if !requirements.languages.isEmpty {
                            Label(
                                requirements.languages.map { $0.uppercased() }.joined(separator: ", "),
                                systemImage: "globe"
                            )
                        }
                    }
                    .font(.subheadline)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
                    .cardStyle()
                }
                .padding(Theme.screenPadding)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Opportunity")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
