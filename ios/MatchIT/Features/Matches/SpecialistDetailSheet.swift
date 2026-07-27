import SwiftUI

/// Full detail for one candidate, so shortlisting is not a decision made on a headline
/// and five chips.
///
/// Shows everything the match payload carries. Bio, languages and certifications are on
/// `SpecialistProfile` but not on `MatchSpecialistView`, so surfacing those needs the
/// backend to widen that schema.
struct SpecialistDetailSheet: View {
    let match: Match
    let onDecision: ((MatchDecision) -> Void)?

    @Environment(\.dismiss) private var dismiss

    private var specialist: MatchSpecialistView { match.specialist }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    header
                    MatchBreakdownView(breakdown: match.breakdown)
                        .padding(4)
                        .cardStyle()

                    if !specialist.skills.isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Skill graph")
                                .font(.subheadline.weight(.semibold))
                            ForEach(specialist.skills) { SkillBar(skill: $0) }
                        }
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .cardStyle()
                    }

                    if let onDecision, match.companyDecision == .pending {
                        HStack(spacing: 10) {
                            Button {
                                onDecision(.rejected)
                                dismiss()
                            } label: {
                                Label("Pass", systemImage: "xmark").frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered)
                            Button {
                                onDecision(.accepted)
                                dismiss()
                            } label: {
                                Label("Shortlist", systemImage: "checkmark").frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(Theme.accent)
                        }
                        .controlSize(.large)
                    }
                }
                .padding(Theme.screenPadding)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Candidate")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(specialist.headline)
                .font(.system(.title3, design: .rounded, weight: .semibold))
            MatchQualityBadge(quality: MatchQuality(score: match.score))
            VStack(alignment: .leading, spacing: 6) {
                Label(
                    "\(specialist.yearsExperience) years of experience",
                    systemImage: "briefcase"
                )
                Label(
                    "\(specialist.country) · \(specialist.remotePreference.displayName)",
                    systemImage: "mappin.and.ellipse"
                )
                if let rate = specialist.hourlyRate {
                    Label("\(Int(rate)) \(specialist.currency) per hour", systemImage: "eurosign.circle")
                }
                Label(
                    "Trust score \(specialist.trustScore.formatted(.number.precision(.fractionLength(0))))/100",
                    systemImage: "checkmark.shield"
                )
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .cardStyle()
    }
}
