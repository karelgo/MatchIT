import SwiftUI

/// Horizontal bar visualising one skill in the skill graph.
struct SkillBar: View {
    let skill: Skill

    var body: some View {
        LevelBar(
            label: SkillName.display(skill.name),
            value: Double(skill.level) / 10,
            trailing: "\(skill.level)/10",
            accessibilityValue: "level \(skill.level) out of 10"
                + (skill.isEvidenced ? ", evidence-backed" : ""),
            badgeSymbol: skill.isEvidenced ? "checkmark.seal.fill" : nil,
            footnote: skill.evidence
        )
    }
}

/// A labelled 0...1 bar. Shared by the skill graph and the match-score breakdown so
/// both read as the same kind of measurement.
struct LevelBar: View {
    let label: String
    let value: Double
    var trailing: String?
    var accessibilityValue: String?
    var tint: Color = Theme.accent
    /// Optional marker beside the label. The skill graph uses it to mark skills backed
    /// by evidence; its meaning is folded into `accessibilityValue` because the whole
    /// bar reads as one element.
    var badgeSymbol: String?
    var footnote: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text(label)
                    .font(.system(.subheadline, design: .rounded, weight: .medium))
                if let badgeSymbol {
                    Image(systemName: badgeSymbol)
                        .font(.caption2)
                        .foregroundStyle(Theme.success)
                }
                Spacer()
                if let trailing {
                    Text(trailing)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.accentSoft)
                    Capsule()
                        .fill(tint)
                        .frame(width: proxy.size.width * min(max(value, 0), 1))
                }
            }
            .frame(height: 8)
            if let footnote {
                Text(footnote)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .lineLimit(2)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(label)
        .accessibilityValue(accessibilityValue ?? "\(Int(value * 100)) percent")
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

/// Circular match indicator. The arc is the raw score; the centre carries the rank
/// where there is one, because a bare percentage in the middle of the range reads as
/// a coin flip even for the best candidate available. `MatchQuality` names the band.
struct ScoreRing: View {
    let score: Double
    var centerText: String?

    @ScaledMetric(relativeTo: .subheadline) private var diameter: CGFloat = 54

    var body: some View {
        ZStack {
            Circle().stroke(Theme.accentSoft, lineWidth: 6)
            Circle()
                .trim(from: 0, to: min(max(score, 0), 1))
                .stroke(MatchQuality(score: score).tint, style: .init(lineWidth: 6, lineCap: .round))
                .rotationEffect(.degrees(-90))
            if let centerText {
                Text(centerText)
                    .font(.system(.subheadline, design: .rounded, weight: .bold))
                    .minimumScaleFactor(0.6)
                    .padding(6)
            }
        }
        .frame(width: diameter, height: diameter)
        .accessibilityHidden(true)
    }
}

/// Flowing, wrapping row of chips.
struct ChipFlow: View {
    let items: [String]

    var body: some View {
        WrapLayout {
            ForEach(items, id: \.self) { TagChip(text: $0) }
        }
        .accessibilityElement(children: .combine)
    }
}

/// Inline failure notice. Placed next to the action that failed rather than at the top
/// of a scroll view, where it can render off-screen and look like nothing happened.
struct ErrorBanner: View {
    let message: String
    var onRetry: (() -> Void)?
    var onDismiss: (() -> Void)?

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
            Text(message)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let onRetry {
                Button("Retry", action: onRetry)
                    .font(.footnote.weight(.semibold))
            }
            if let onDismiss {
                Button {
                    onDismiss()
                } label: {
                    Image(systemName: "xmark")
                }
                .accessibilityLabel("Dismiss error")
            }
        }
        .font(.footnote)
        .foregroundStyle(.white)
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.danger, in: .rect(cornerRadius: 10))
        .buttonStyle(.plain)
        .accessibilityElement(children: .contain)
    }
}
