import SwiftUI

struct RootView: View {
    @State private var session: SessionStore

    init(api: APIClient) {
        _session = State(initialValue: SessionStore(api: api))
    }

    var body: some View {
        Group {
            switch session.state {
            case .loading:
                ProgressView("MatchIT")
                    .task { await session.bootstrap() }
            case .signedOut:
                AuthView(api: session.api) { response in
                    session.didAuthenticate(response)
                }
            case let .signedIn(user):
                home(for: user)
            }
        }
        .tint(Theme.accent)
    }

    @ViewBuilder
    private func home(for user: User) -> some View {
        if user.role.isSpecialist {
            TabView {
                MatchDeckView(api: session.api)
                    .tabItem { Label("Opportunities", systemImage: "rectangle.stack.fill") }
                ProfileView(api: session.api, user: user) {
                    Task { await session.signOut() }
                }
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }
            }
        } else {
            TabView {
                ConciergeView(api: session.api)
                    .tabItem { Label("Concierge", systemImage: "sparkles") }
                AccountView(user: user) {
                    Task { await session.signOut() }
                }
                .tabItem { Label("Account", systemImage: "person.crop.circle") }
            }
        }
    }
}

/// Minimal account screen for company-side users.
struct AccountView: View {
    let user: User
    let onSignOut: () -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section("Signed in as") {
                    LabeledContent("Name", value: user.fullName)
                    LabeledContent("Email", value: user.email)
                    LabeledContent("Role", value: user.role.displayName)
                }
                Section {
                    Button("Sign out", role: .destructive) { onSignOut() }
                }
            }
            .navigationTitle("Account")
        }
    }
}
