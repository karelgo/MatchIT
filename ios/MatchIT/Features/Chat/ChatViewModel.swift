import Foundation
import Observation

/// One chat thread. Loads history over REST, then streams live messages over the
/// WebSocket. Sends go over the socket when it is up and fall back to REST when
/// it is not, so a message is never silently lost.
@MainActor
@Observable
final class ChatViewModel {
    let conversation: Conversation
    let currentUserId: UUID

    var messages: [ChatMessage] = []
    var draft = ""
    var isLoading = false
    var isLive = false
    var errorMessage: String?

    private let api: APIClient
    private let socket = ChatSocket()
    private var streamTask: Task<Void, Never>?

    init(api: APIClient, conversation: Conversation, currentUserId: UUID) {
        self.api = api
        self.conversation = conversation
        self.currentUserId = currentUserId
    }

    var canSend: Bool {
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    func start() async {
        isLoading = true
        defer { isLoading = false }
        do {
            messages = try await api.messages(conversationId: conversation.id)
        } catch {
            errorMessage = error.localizedDescription
        }
        connect()
    }

    func stop() {
        streamTask?.cancel()
        streamTask = nil
        socket.disconnect()
        isLive = false
    }

    private func connect() {
        streamTask?.cancel()
        streamTask = Task { [weak self] in
            guard let self else { return }
            do {
                let url = try await self.api.chatSocketURL(conversationId: self.conversation.id)
                let stream = self.socket.connect(to: url)
                self.isLive = true
                for try await message in stream {
                    self.append(message)
                }
                self.isLive = false
            } catch is CancellationError {
                self.isLive = false
            } catch {
                // The thread still works over REST; surface the degraded state
                // rather than an alarming error.
                self.isLive = false
            }
        }
    }

    /// Inserts keeping chronological order and ignoring duplicates — the sender
    /// receives its own message back as the server's delivery echo.
    private func append(_ message: ChatMessage) {
        guard !messages.contains(where: { $0.id == message.id }) else { return }
        let index = messages.firstIndex { $0.createdAt > message.createdAt } ?? messages.endIndex
        messages.insert(message, at: index)
    }

    func send() async {
        let content = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else { return }
        draft = ""
        do {
            if isLive {
                try await socket.send(content)
            } else {
                append(try await api.sendMessage(conversationId: conversation.id, content: content))
            }
        } catch {
            draft = content  // give the text back so the user can retry
            errorMessage = error.localizedDescription
        }
    }

    func isMine(_ message: ChatMessage) -> Bool {
        message.senderId == currentUserId
    }
}
