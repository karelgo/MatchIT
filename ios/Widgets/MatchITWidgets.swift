import ActivityKit
import SwiftUI
import WidgetKit

@main
struct MatchITWidgetBundle: WidgetBundle {
    var body: some Widget {
        OpportunitiesWidget()
        InterviewLiveActivity()
    }
}

// MARK: - Opportunities widget

struct OpportunitiesEntry: TimelineEntry {
    let date: Date
    let snapshot: WidgetSnapshot
}

struct OpportunitiesProvider: TimelineProvider {
    func placeholder(in context: Context) -> OpportunitiesEntry {
        OpportunitiesEntry(date: .now, snapshot: .placeholder)
    }

    func getSnapshot(in context: Context, completion: @escaping (OpportunitiesEntry) -> Void) {
        completion(OpportunitiesEntry(date: .now, snapshot: SharedStore.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<OpportunitiesEntry>) -> Void) {
        let entry = OpportunitiesEntry(date: .now, snapshot: SharedStore.load())
        // The app refreshes the snapshot (and reloads timelines) whenever the
        // deck loads; this interval only bounds staleness while the app is idle.
        let refresh = Calendar.current.date(byAdding: .minute, value: 30, to: .now) ?? .now
        completion(Timeline(entries: [entry], policy: .after(refresh)))
    }
}

struct OpportunitiesWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: OpportunitiesEntry

    private let accent = Color(red: 0.29, green: 0.33, blue: 0.95)

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Image(systemName: "sparkles")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(accent)
                Text("MatchIT")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
            }
            Spacer(minLength: 0)
            Text("\(entry.snapshot.opportunityCount)")
                .font(.system(size: 34, weight: .bold, design: .rounded))
                .contentTransition(.numericText())
            Text(entry.snapshot.opportunityCount == 1 ? "opportunity" : "opportunities")
                .font(.caption)
                .foregroundStyle(.secondary)
            if family != .systemSmall, let title = entry.snapshot.topOpportunityTitle {
                Divider()
                HStack {
                    Text(title)
                        .font(.caption.weight(.medium))
                        .lineLimit(1)
                    Spacer()
                    if let score = entry.snapshot.topScore {
                        Text(score, format: .percent.precision(.fractionLength(0)))
                            .font(.caption.monospacedDigit().weight(.semibold))
                            .foregroundStyle(accent)
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
    }
}

struct OpportunitiesWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: SharedStore.widgetKind, provider: OpportunitiesProvider()) { entry in
            OpportunitiesWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Opportunities")
        .description("Your matched opportunities at a glance.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

// MARK: - Interview Live Activity

struct InterviewLiveActivity: Widget {
    private let accent = Color(red: 0.29, green: 0.33, blue: 0.95)

    var body: some WidgetConfiguration {
        ActivityConfiguration(for: InterviewActivityAttributes.self) { context in
            // Lock screen / banner
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label(context.attributes.title, systemImage: "sparkles")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Text("\(context.state.answeredCount)/\(context.state.totalQuestions)")
                        .font(.subheadline.monospacedDigit().weight(.bold))
                }
                ProgressView(value: context.state.progress)
                    .tint(accent)
                Text("Now: \(context.state.currentSkill.capitalized)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .activityBackgroundTint(Color(.systemBackground).opacity(0.8))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Label("Interview", systemImage: "sparkles")
                        .font(.caption.weight(.semibold))
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text("\(context.state.answeredCount)/\(context.state.totalQuestions)")
                        .font(.caption.monospacedDigit().weight(.bold))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 4) {
                        ProgressView(value: context.state.progress).tint(accent)
                        Text(context.state.currentSkill.capitalized)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            } compactLeading: {
                Image(systemName: "sparkles").foregroundStyle(accent)
            } compactTrailing: {
                Text("\(context.state.answeredCount)/\(context.state.totalQuestions)")
                    .font(.caption2.monospacedDigit())
            } minimal: {
                Image(systemName: "sparkles").foregroundStyle(accent)
            }
        }
    }
}
