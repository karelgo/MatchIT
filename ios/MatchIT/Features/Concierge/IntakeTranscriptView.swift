import SwiftUI

/// The intake conversation so far.
///
/// The concierge is a multi-turn feature and the assignment carries its full history,
/// but without this the only thing on screen is the newest set of questions — so people
/// cannot see what they already told it, or what it asked two rounds ago.
struct IntakeTranscriptView: View {
    let history: [IntakeMessage]
    @State private var isExpanded = false

    var body: some View {
        if !history.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { isExpanded.toggle() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "bubble.left.and.bubble.right")
                        Text(isExpanded ? "Hide conversation" : "Show conversation (\(history.count))")
                        Spacer()
                        Image(systemName: "chevron.down")
                            .rotationEffect(.degrees(isExpanded ? 0 : -90))
                            .font(.caption.weight(.semibold))
                    }
                    .font(.subheadline.weight(.medium))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(isExpanded ? "Hide conversation" : "Show conversation")

                if isExpanded {
                    ForEach(Array(history.enumerated()), id: \.offset) { _, message in
                        TranscriptBubble(message: message)
                    }
                }
            }
        }
    }
}

private struct TranscriptBubble: View {
    let message: IntakeMessage

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(message.isCompany ? "You" : "Concierge")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(message.isCompany ? .secondary : Theme.accent)
            Text(message.content)
                .font(.subheadline)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(
                    message.isCompany ? Color(.tertiarySystemFill) : Theme.accentSoft,
                    in: .rect(cornerRadius: 12)
                )
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(message.isCompany ? "You said" : "Concierge asked"): \(message.content)")
    }
}
