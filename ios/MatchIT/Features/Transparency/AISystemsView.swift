import Observation
import SwiftUI

@MainActor
@Observable
final class AISystemsViewModel {
    var document: AISystemsDocument?
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
            document = try await api.aiSystems()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Every automated system in the product, with its purpose, inputs, limitations and
/// the oversight applied to it. Article 50 of the EU AI Act requires telling people
/// they are dealing with an AI system; this is that disclosure, in the app.
struct AISystemsView: View {
    @State private var model: AISystemsViewModel

    init(api: APIClient) {
        _model = State(initialValue: AISystemsViewModel(api: api))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let message = model.errorMessage {
                    ErrorBanner(message: message, onRetry: { Task { await model.load() } })
                }
                if model.isLoading {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                } else if let document = model.document {
                    Text(document.statement)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .padding()
                        .cardStyle()
                    ForEach(document.systems) { system in
                        card(system)
                    }
                }
            }
            .padding(Theme.screenPadding)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("AI systems")
        .navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
    }

    private func card(_ system: AISystemCard) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(system.name).font(.system(.headline, design: .rounded))
                Spacer()
                TagChip(text: system.kind)
            }
            Text(system.purpose).font(.subheadline)

            section("What it reads", system.inputs, systemImage: "arrow.down.circle")
            labelled("What it is used for", system.usedFor)
            labelled("Human oversight", system.humanOversight)
            section("Limitations", system.limitations, systemImage: "exclamationmark.circle")
            section("Personal data", system.personalData, systemImage: "person.crop.circle.badge.questionmark")

            Text(system.definitionFingerprint)
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)
                .accessibilityLabel("Definition fingerprint \(system.definitionFingerprint)")
        }
        .padding()
        .cardStyle()
    }

    private func section(_ title: String, _ items: [String], systemImage: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption.weight(.semibold))
            ForEach(items, id: \.self) { item in
                Label(item, systemImage: systemImage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func labelled(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption.weight(.semibold))
            Text(body).font(.caption).foregroundStyle(.secondary)
        }
    }
}
