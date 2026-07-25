import SwiftUI

struct AuthView: View {
    @State private var model: AuthViewModel

    init(api: APIClient, onAuthenticated: @escaping (TokenResponse) -> Void) {
        _model = State(initialValue: AuthViewModel(api: api, onAuthenticated: onAuthenticated))
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                header
                Picker("Mode", selection: $model.mode) {
                    ForEach(AuthViewModel.Mode.allCases, id: \.self) { Text($0.rawValue) }
                }
                .pickerStyle(.segmented)

                VStack(spacing: 14) {
                    if model.mode == .register {
                        TextField("Full name", text: $model.fullName)
                            .textContentType(.name)
                        rolePicker
                    }
                    TextField("Email", text: $model.email)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .textContentType(.emailAddress)
                    SecureField("Password (10+ characters)", text: $model.password)
                        .textContentType(model.mode == .register ? .newPassword : .password)
                }
                .textFieldStyle(.roundedBorder)

                if let message = model.errorMessage {
                    ErrorBanner(message: message)
                }

                Button {
                    Task { await model.submit() }
                } label: {
                    if model.isBusy {
                        ProgressView().tint(.white)
                    } else {
                        Text(model.mode.rawValue)
                    }
                }
                .buttonStyle(.primary)
                .disabled(!model.canSubmit || model.isBusy)
            }
            .padding(Theme.screenPadding)
        }
        .background(Color(.systemGroupedBackground))
    }

    private var header: some View {
        VStack(spacing: 8) {
            Image(systemName: "sparkles.rectangle.stack.fill")
                .font(.system(size: 44))
                .foregroundStyle(Theme.accent)
            Theme.title("MatchIT")
            Text("AI staffing. Hire specialists in minutes, not weeks.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 40)
    }

    private var rolePicker: some View {
        HStack {
            Text("I am a").foregroundStyle(.secondary)
            Spacer()
            Picker("Role", selection: $model.role) {
                ForEach([UserRole.freelancer, .employee, .consultancy, .hiringManager, .recruiter], id: \.self) {
                    Text($0.displayName)
                }
            }
        }
        .padding(.vertical, 2)
    }
}
