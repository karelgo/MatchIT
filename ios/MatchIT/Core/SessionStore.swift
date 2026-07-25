import Foundation
import Observation

enum SessionState: Equatable, Sendable {
    case loading
    case signedOut
    case signedIn(User)
}

/// Owns the authenticated user and drives root navigation.
@MainActor
@Observable
final class SessionStore {
    private(set) var state: SessionState = .loading
    let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func bootstrap() async {
        guard await api.hasSession else {
            state = .signedOut
            return
        }
        do {
            state = .signedIn(try await api.me())
        } catch {
            state = .signedOut
        }
    }

    func didAuthenticate(_ response: TokenResponse) {
        state = .signedIn(response.user)
    }

    func signOut() async {
        await api.signOut()
        state = .signedOut
    }
}
