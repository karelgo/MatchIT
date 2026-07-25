import Foundation
import Observation

@MainActor
@Observable
final class AuthViewModel {
    enum Mode: String, CaseIterable {
        case signIn = "Sign In"
        case register = "Create Account"
    }

    var mode: Mode = .signIn
    var email = ""
    var password = ""
    var fullName = ""
    var role: UserRole = .freelancer
    var isBusy = false
    var errorMessage: String?

    private let api: APIClient
    private let onAuthenticated: (TokenResponse) -> Void

    init(api: APIClient, onAuthenticated: @escaping (TokenResponse) -> Void) {
        self.api = api
        self.onAuthenticated = onAuthenticated
    }

    var canSubmit: Bool {
        guard email.contains("@"), password.count >= 10 else { return false }
        return mode == .signIn || !fullName.trimmingCharacters(in: .whitespaces).isEmpty
    }

    func submit() async {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            let response: TokenResponse
            switch mode {
            case .signIn:
                response = try await api.login(email: email, password: password)
            case .register:
                response = try await api.register(
                    email: email, password: password, fullName: fullName, role: role
                )
            }
            onAuthenticated(response)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
