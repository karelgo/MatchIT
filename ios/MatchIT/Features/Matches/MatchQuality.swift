import SwiftUI

/// How a composite match score is described to people.
///
/// The engine's composite blends six factors, one of which (semantic similarity) rarely
/// approaches 1.0, so real scores cluster around the middle of the range: a genuinely
/// strong candidate lands near 0.55. Rendered as a bare percentage that reads as a coin
/// flip on every card, which quietly contradicts the product's promise. Naming the band
/// and showing the rank carries the meaning; `MatchBreakdownView` carries the detail.
enum MatchQuality {
    case strong
    case good
    case possible

    init(score: Double) {
        switch score {
        case 0.55...: self = .strong
        case 0.45 ..< 0.55: self = .good
        default: self = .possible
        }
    }

    var label: String {
        switch self {
        case .strong: "Strong fit"
        case .good: "Good fit"
        case .possible: "Possible fit"
        }
    }

    var tint: Color {
        switch self {
        case .strong: Theme.success
        case .good: Theme.accent
        case .possible: .secondary
        }
    }
}

struct MatchQualityBadge: View {
    let quality: MatchQuality

    var body: some View {
        Text(quality.label)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(quality.tint.opacity(0.14), in: .capsule)
            .foregroundStyle(quality.tint)
    }
}

/// "Why this match" — the per-factor scores the engine already returns for every match.
///
/// Percentages belong here rather than on the ring: "Rate 100%" is meaningful and
/// commonly hit, and seeing which factors are strong is what makes a composite score
/// trustworthy instead of opaque.
struct MatchBreakdownView: View {
    let breakdown: [String: Double]

    /// Most decision-relevant first, rather than whatever order the dictionary yields.
    private static let preferredOrder = [
        "skills", "semantic", "rate", "availability", "location", "language",
    ]

    private static let labels = [
        "skills": "Skills",
        "semantic": "Relevance",
        "rate": "Rate",
        "availability": "Availability",
        "location": "Location",
        "language": "Language",
    ]

    private var rows: [(key: String, label: String, value: Double)] {
        let known = Self.preferredOrder.compactMap { key -> (String, String, Double)? in
            guard let value = breakdown[key] else { return nil }
            return (key, Self.labels[key] ?? key.capitalized, value)
        }
        // Anything the backend adds later still shows up rather than silently vanishing.
        let extra = breakdown.keys
            .filter { !Self.preferredOrder.contains($0) }
            .sorted()
            .map { ($0, Self.labels[$0] ?? $0.capitalized, breakdown[$0] ?? 0) }
        return (known + extra).map { (key: $0.0, label: $0.1, value: $0.2) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Why this match")
                .font(.subheadline.weight(.semibold))
            ForEach(rows, id: \.key) { row in
                LevelBar(
                    label: row.label,
                    value: row.value,
                    trailing: row.value.formatted(.percent.precision(.fractionLength(0))),
                    tint: MatchQuality(score: row.value).tint
                )
            }
        }
        .padding(12)
        .background(Theme.nestedSurface, in: .rect(cornerRadius: 12))
    }
}
