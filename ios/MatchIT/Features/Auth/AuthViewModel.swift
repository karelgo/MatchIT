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
    var isPasswordVisible = false

    private static let minimumPasswordLength = 10

    private let api: APIClient
    private let onAuthenticated: (TokenResponse) -> Void

    init(api: APIClient, onAuthenticated: @escaping (TokenResponse) -> Void) {
        self.api = api
        self.onAuthenticated = onAuthenticated
    }

    var canSubmit: Bool {
        guard email.contains("@"), password.count >= Self.minimumPasswordLength else { return false }
        return mode == .signIn || !fullName.trimmingCharacters(in: .whitespaces).isEmpty
    }

    /// Says why the button is disabled. A silently inert control leaves people guessing —
    /// the 10-character rule was only ever visible in a placeholder.
    var validationHint: String? {
        if !email.isEmpty, !email.contains("@") {
            return "That email address looks incomplete."
        }
        if !password.isEmpty, password.count < Self.minimumPasswordLength {
            let remaining = Self.minimumPasswordLength - password.count
            return "Password needs \(remaining) more character\(remaining == 1 ? "" : "s")."
        }
        if mode == .register,
           fullName.trimmingCharacters(in: .whitespaces).isEmpty,
           !email.isEmpty || !password.isEmpty {
            return "Add your full name to continue."
        }
        return nil
    }

    /// What picking this role actually changes, stated at the moment of choosing. It
    /// determines the whole experience and cannot be changed later in the app.
    var roleExplanation: String {
        role.isSpecialist
            ? "You'll receive matched assignments and accept or pass on them."
            : "You'll describe problems to the AI concierge and review ranked specialists."
    }

    func modeChanged() {
        errorMessage = nil
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
