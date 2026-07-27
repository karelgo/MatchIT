import Foundation

/// Thin wrapper over `URLSessionWebSocketTask` exposing inbound messages as an
/// async stream. Main-actor bound because it is driven entirely by chat UI.
@MainActor
final class ChatSocket {
    private var task: URLSessionWebSocketTask?
    private let session = URLSession(configuration: .default)

    var isConnected: Bool { task != nil }

    /// Opens the socket and streams decoded messages until the connection drops.
    func connect(to url: URL) -> AsyncThrowingStream<ChatMessage, Error> {
        disconnect()
        let task = session.webSocketTask(with: url)
        self.task = task
        task.resume()

        return AsyncThrowingStream { continuation in
            let pump = Task {
                let decoder = JSONDecoder()
                decoder.keyDecodingStrategy = .convertFromSnakeCase
                decoder.dateDecodingStrategy = .matchITTimestamp
                do {
                    while !Task.isCancelled {
                        switch try await task.receive() {
                        case let .string(text):
                            continuation.yield(try decoder.decode(ChatMessage.self, from: Data(text.utf8)))
                        case let .data(data):
                            continuation.yield(try decoder.decode(ChatMessage.self, from: data))
                        @unknown default:
                            continue
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in pump.cancel() }
        }
    }

    func send(_ content: String) async throws {
        guard let task else { throw APIError.unauthorized }
        let payload = try JSONEncoder().encode(["content": content])
        try await task.send(.string(String(decoding: payload, as: UTF8.self)))
    }

    func disconnect() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
    }
}
