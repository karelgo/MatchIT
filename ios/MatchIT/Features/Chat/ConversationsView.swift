import Observation
import SwiftUI

@MainActor
@Observable
final class ConversationsViewModel {
    var conversations: [Conversation] = []
    var isLoading = false
    var errorMessage: String?

    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            conversations = try await api.conversations()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ConversationsView: View {
    @State private var model: ConversationsViewModel
    private let api: APIClient
    private let currentUserId: UUID

    init(api: APIClient, currentUserId: UUID) {
        self.api = api
        self.currentUserId = currentUserId
        _model = State(initialValue: ConversationsViewModel(api: api))
    }

    var body: some View {
        NavigationStack {
            Group {
                if model.isLoading, model.conversations.isEmpty {
                    ProgressView()
                } else if model.conversations.isEmpty {
                    ContentUnavailableView(
                        "No matches yet",
                        systemImage: "bubble.left.and.bubble.right",
                        description: Text("When both sides accept, your chat opens here.")
                    )
                } else {
                    List(model.conversations) { conversation in
                        NavigationLink {
                            ChatView(
                                api: api,
                                conversation: conversation,
                                currentUserId: currentUserId
                            )
                        } label: {
                            ConversationRow(conversation: conversation)
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Messages")
            .task { await model.load() }
            .refreshable { await model.load() }
            .overlay(alignment: .top) {
                if let message = model.errorMessage {
                    ErrorBanner(message: message).padding()
                }
            }
        }
    }
}

struct ConversationRow: View {
    let conversation: Conversation

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(Theme.accentSoft)
                .frame(width: 44, height: 44)
                .overlay {
                    Text(conversation.counterpartName.prefix(1).uppercased())
                        .font(.system(.headline, design: .rounded))
                        .foregroundStyle(Theme.accent)
                }
            VStack(alignment: .leading, spacing: 3) {
                Text(conversation.counterpartName)
                    .font(.headline)
                Text(conversation.lastMessage ?? conversation.assignmentTitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            if let at = conversation.lastMessageAt {
                Text(at, format: .dateTime.hour().minute())
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 4)
    }
}
