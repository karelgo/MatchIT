import SwiftUI

/// The engagement evidence pack. Indicators on screen, the full document to share.
///
/// Deliberately presented as evidence rather than as a verdict: the pack says what
/// the platform observed and which way each observation points, and stops there.
/// Misclassification is judged on the relationship as a whole, and a checklist that
/// implied otherwise would be worse than useless to whoever relied on it.
struct EvidencePackSheet: View {
    let pack: EvidencePack

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(pack.pack.disclaimer)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .padding()
                        .background(Color.orange.opacity(0.12), in: .rect(cornerRadius: 12))

                    if !pack.pack.scopeOfWork.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Contracted scope").font(.system(.headline, design: .rounded))
                            ForEach(pack.pack.scopeOfWork, id: \.self) { item in
                                Text("• \(item)").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .padding()
                        .cardStyle()
                    }

                    VStack(alignment: .leading, spacing: 14) {
                        Text("Independence indicators")
                            .font(.system(.headline, design: .rounded))
                        ForEach(pack.pack.indicators) { indicator in
                            row(indicator)
                        }
                    }
                    .padding()
                    .cardStyle()
                }
                .padding(Theme.screenPadding)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Evidence pack")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    ShareLink(item: pack.markdown) {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .accessibilityLabel("Share the full pack")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private func row(_ indicator: EvidenceIndicator) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: symbol(indicator.direction))
                    .foregroundStyle(tint(indicator.direction))
                    .font(.caption)
                Text(indicator.label).font(.subheadline.weight(.medium))
                Spacer()
            }
            Text(indicator.observed).font(.caption)
            Text(indicator.why).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 10))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(indicator.label): \(indicator.observed)")
    }

    private func symbol(_ direction: String) -> String {
        switch direction {
        case "supports_independence": "checkmark.circle.fill"
        case "points_the_other_way": "exclamationmark.triangle.fill"
        default: "circle"
        }
    }

    private func tint(_ direction: String) -> Color {
        switch direction {
        case "supports_independence": Theme.success
        case "points_the_other_way": .orange
        default: .secondary
        }
    }
}
