import Observation
import SwiftUI

@MainActor
@Observable
final class PrivacyViewModel {
    var isBusy = false
    var exportedJSON: String?
    var errorMessage: String?
    var confirmingDeletion = false

    private let api: APIClient
    private let onDeleted: () -> Void

    init(api: APIClient, onDeleted: @escaping () -> Void) {
        self.api = api
        self.onDeleted = onDeleted
    }

    func export() async {
        isBusy = true
        defer { isBusy = false }
        do {
            exportedJSON = try await api.exportMyData()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func delete() async {
        isBusy = true
        defer { isBusy = false }
        do {
            try await api.deleteMyAccount()
            onDeleted()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// GDPR controls, shared by the specialist and company account screens.
struct PrivacySection: View {
    @State private var model: PrivacyViewModel

    init(api: APIClient, onDeleted: @escaping () -> Void) {
        _model = State(initialValue: PrivacyViewModel(api: api, onDeleted: onDeleted))
    }

    var body: some View {
        Section {
            Button {
                Task { await model.export() }
            } label: {
                Label("Download my data", systemImage: "square.and.arrow.down")
            }
            .disabled(model.isBusy)

            Button(role: .destructive) {
                model.confirmingDeletion = true
            } label: {
                Label("Delete my account", systemImage: "trash")
            }
            .disabled(model.isBusy)

            if let message = model.errorMessage {
                Text(message).font(.caption).foregroundStyle(Theme.danger)
            }
        } header: {
            Text("Privacy")
        } footer: {
            Text(
                "Download everything we hold about you, or delete your account permanently. An active contract must be completed or cancelled first."
            )
        }
        .alert("Delete your account?", isPresented: $model.confirmingDeletion) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) { Task { await model.delete() } }
        } message: {
            Text("This erases your profile, matches, interviews and messages. It cannot be undone.")
        }
        .sheet(isPresented: .init(get: { model.exportedJSON != nil }, set: { if !$0 { model.exportedJSON = nil } })) {
            NavigationStack {
                ScrollView {
                    Text(model.exportedJSON ?? "")
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                }
                .navigationTitle("Your data")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Done") { model.exportedJSON = nil }
                    }
                }
            }
        }
    }
}
