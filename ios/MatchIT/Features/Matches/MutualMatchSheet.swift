import SwiftUI

/// Confirmation for a mutual match.
///
/// This is the moment the whole product exists to produce, and it previously passed as a
/// haptic and a card sliding away. The copy deliberately claims nothing that is not built:
/// interviewing and contracting are on the roadmap, so this states the facts of the match
/// and stops there. Extend it when those steps actually exist.
struct MutualMatchSheet: View {
    let match: Match
    let onDone: () -> Void

    private var requirements: AssignmentRequirements { match.assignment.requirements }

    private var roleTitle: String {
        requirements.roles.first.map { SkillName.display($0.title) } ?? "this assignment"
    }

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 64))
                .foregroundStyle(Theme.success)
                .accessibilityHidden(true)

            VStack(spacing: 8) {
                Text("It's a match")
                    .font(.system(.largeTitle, design: .rounded, weight: .bold))
                Text("You and the company both accepted \(roleTitle).")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            .accessibilityElement(children: .combine)

            VStack(alignment: .leading, spacing: 10) {
                Text("The assignment")
                    .font(.subheadline.weight(.semibold))
                if let max = requirements.budget.maxHourly {
                    fact("eurosign.circle", "Up to \(Int(max)) \(requirements.budget.currency) per hour")
                }
                if let weeks = requirements.durationWeeks {
                    fact("calendar", "About \(weeks) weeks")
                }
                fact(
                    requirements.remoteAllowed ? "wifi" : "building.2",
                    requirements.remoteAllowed ? "Remote allowed" : "On-site"
                )
                if let country = requirements.country {
                    fact("mappin.and.ellipse", country)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 14))

            Spacer(minLength: 0)

            Button("Keep reviewing", action: onDone)
                .buttonStyle(.primary)
        }
        .padding(Theme.screenPadding)
        .background(Color(.systemGroupedBackground))
    }

    private func fact(_ symbol: String, _ text: String) -> some View {
        Label(text, systemImage: symbol)
            .font(.subheadline)
            .accessibilityElement(children: .combine)
    }
}
