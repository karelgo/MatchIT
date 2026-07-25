import SwiftUI

/// Horizontal bar visualising one skill in the skill graph.
struct SkillBar: View {
    let skill: Skill

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(skill.name.capitalized)
                    .font(.system(.subheadline, design: .rounded, weight: .medium))
                Spacer()
                Text("\(skill.level)/10")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.accentSoft)
                    Capsule()
                        .fill(Theme.accent)
                        .frame(width: proxy.size.width * CGFloat(skill.level) / 10)
                }
            }
            .frame(height: 8)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(skill.name), level \(skill.level) out of 10")
    }
}

/// Small rounded tag, used for skills and languages.
struct TagChip: View {
    let text: String
    var prominent = false

    var body: some View {
        Text(text)
            .font(.system(.caption, design: .rounded, weight: .medium))
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(prominent ? Theme.accent : Color(.tertiarySystemFill), in: .capsule)
            .foregroundStyle(prominent ? .white : .primary)
    }
}

/// Circular match-score indicator (0...1).
struct ScoreRing: View {
    let score: Double

    var body: some View {
        ZStack {
            Circle().stroke(Theme.accentSoft, lineWidth: 6)
            Circle()
                .trim(from: 0, to: score)
                .stroke(Theme.accent, style: .init(lineWidth: 6, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text(score, format: .percent.precision(.fractionLength(0)))
                .font(.system(.subheadline, design: .rounded, weight: .bold))
        }
        .accessibilityLabel("Match score \(Int(score * 100)) percent")
    }
}

/// Simple flowing layout for chips.
struct ChipFlow: View {
    let items: [String]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(items, id: \.self) { TagChip(text: $0) }
            }
        }
    }
}

struct ErrorBanner: View {
    let message: String

    var body: some View {
        Label(message, systemImage: "exclamationmark.triangle.fill")
            .font(.footnote)
            .foregroundStyle(.white)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.danger, in: .rect(cornerRadius: 10))
    }
}
