import SwiftUI

struct ChatView: View {
    @State private var model: ChatViewModel

    init(api: APIClient, conversation: Conversation, currentUserId: UUID) {
        _model = State(
            initialValue: ChatViewModel(
                api: api, conversation: conversation, currentUserId: currentUserId
            )
        )
    }

    var body: some View {
        VStack(spacing: 0) {
            if let message = model.errorMessage {
                ErrorBanner(message: message).padding(.horizontal)
            }
            transcript
            composer
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle(model.conversation.counterpartName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                VStack(spacing: 1) {
                    Text(model.conversation.counterpartName)
                        .font(.headline)
                    Text(model.isLive ? "Live" : model.conversation.assignmentTitle)
                        .font(.caption2)
                        .foregroundStyle(model.isLive ? Theme.success : .secondary)
                }
            }
        }
        .task { await model.start() }
        .onDisappear { model.stop() }
    }

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 10) {
                    if model.isLoading {
                        ProgressView().padding()
                    }
                    if model.messages.isEmpty, !model.isLoading {
                        ContentUnavailableView(
                            "Say hello",
                            systemImage: "hand.wave",
                            description: Text(
                                "You matched on \(model.conversation.assignmentTitle). Start the conversation."
                            )
                        )
                        .padding(.top, 40)
                    }
                    ForEach(model.messages) { message in
                        MessageBubble(message: message, isMine: model.isMine(message))
                            .id(message.id)
                    }
                }
                .padding(.horizontal, Theme.screenPadding)
                .padding(.vertical, 12)
            }
            .onChange(of: model.messages.count) {
                guard let last = model.messages.last else { return }
                withAnimation(.easeOut(duration: 0.2)) {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
        }
    }

    private var composer: some View {
        HStack(spacing: 10) {
            TextField("Message", text: $model.draft, axis: .vertical)
                .lineLimit(1 ... 5)
                .textFieldStyle(.roundedBorder)
                .onSubmit { Task { await model.send() } }
            Button {
                Task { await model.send() }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title)
                    .foregroundStyle(model.canSend ? Theme.accent : Color(.tertiaryLabel))
            }
            .disabled(!model.canSend)
            .accessibilityLabel("Send message")
        }
        .padding(.horizontal, Theme.screenPadding)
        .padding(.vertical, 10)
        .background(.bar)
    }
}

struct MessageBubble: View {
    let message: ChatMessage
    let isMine: Bool

    var body: some View {
        HStack {
            if isMine { Spacer(minLength: 50) }
            VStack(alignment: isMine ? .trailing : .leading, spacing: 3) {
                Text(message.content)
                    .padding(.horizontal, 13)
                    .padding(.vertical, 9)
                    .background(
                        isMine ? Theme.accent : Color(.secondarySystemGroupedBackground),
                        in: .rect(cornerRadius: 16)
                    )
                    .foregroundStyle(isMine ? .white : .primary)
                Text(message.createdAt, format: .dateTime.hour().minute())
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            if !isMine { Spacer(minLength: 50) }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(isMine ? "You" : message.senderName): \(message.content)")
    }
}
