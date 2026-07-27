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
                        .autocorrectionDisabled()
                    passwordField
                }
                .textFieldStyle(.roundedBorder)

                if let hint = model.validationHint {
                    Text(hint)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityAddTraits(.isStaticText)
                }

                if let message = model.errorMessage {
                    ErrorBanner(message: message, onDismiss: { model.errorMessage = nil })
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
        .onChange(of: model.mode) { model.modeChanged() }
    }

    /// Reveal toggle: a 10-character minimum typed blind on a phone keyboard is a
    /// needless source of failed sign-ins.
    private var passwordField: some View {
        HStack(spacing: 8) {
            Group {
                if model.isPasswordVisible {
                    TextField("Password (10+ characters)", text: $model.password)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } else {
                    SecureField("Password (10+ characters)", text: $model.password)
                }
            }
            .textContentType(model.mode == .register ? .newPassword : .password)

            Button {
                model.isPasswordVisible.toggle()
            } label: {
                Image(systemName: model.isPasswordVisible ? "eye.slash" : "eye")
                    .frame(width: 44, height: 44)
                    .contentShape(.rect)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .accessibilityLabel(model.isPasswordVisible ? "Hide password" : "Show password")
        }
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
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("I am a").foregroundStyle(.secondary)
                Spacer()
                Picker("Role", selection: $model.role) {
                    ForEach([UserRole.freelancer, .employee, .consultancy, .hiringManager, .recruiter], id: \.self) {
                        Text($0.displayName)
                    }
                }
            }
            Text(model.roleExplanation)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 2)
    }
}
