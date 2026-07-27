import SwiftUI
import UniformTypeIdentifiers

struct ProfileView: View {
    @State private var model: ProfileViewModel
    @State private var showingCVPicker = false

    init(api: APIClient, user: User, onSignOut: @escaping () -> Void) {
        _model = State(initialValue: ProfileViewModel(api: api, user: user, onSignOut: onSignOut))
    }

    var body: some View {
        NavigationStack {
            Form {
                if let message = model.errorMessage {
                    Section { ErrorBanner(message: message) }
                }
                if let trust = model.trustScore {
                    Section {
                        Label(
                            "Trust score \(trust, format: .number.precision(.fractionLength(0)))/100",
                            systemImage: "checkmark.shield.fill"
                        )
                        .foregroundStyle(Theme.success)
                    }
                }

                Section("About you") {
                    TextField("Headline (e.g. Azure Data Architect)", text: $model.draft.headline)
                    TextField("Bio", text: $model.draft.bio, axis: .vertical)
                        .lineLimit(3 ... 6)
                    Stepper(
                        "Experience: \(model.draft.yearsExperience) years",
                        value: $model.draft.yearsExperience, in: 0 ... 50
                    )
                }

                Section("Skill graph") {
                    ForEach(model.draft.skills) { skill in
                        SkillBar(skill: skill)
                            .swipeActions {
                                Button("Remove", role: .destructive) { model.removeSkill(skill) }
                            }
                    }
                    HStack {
                        TextField("Add skill", text: $model.newSkillName)
                            .onSubmit { model.addSkill() }
                        Picker("", selection: $model.newSkillLevel) {
                            ForEach(1 ... 10, id: \.self) { Text("\($0)") }
                        }
                        .labelsHidden()
                        Button("Add") { model.addSkill() }
                            .disabled(model.newSkillName.isEmpty)
                    }
                }

                Section {
                    Button {
                        showingCVPicker = true
                    } label: {
                        Label("Import CV (PDF)", systemImage: "doc.badge.arrow.up")
                    }
                    .disabled(model.isImporting)
                    HStack {
                        TextField("GitHub username", text: $model.githubUsername)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                        Button("Analyse") { Task { await model.importGitHub() } }
                            .disabled(model.githubUsername.isEmpty || model.isImporting)
                    }
                    if model.isImporting {
                        Label("The AI is reading the evidence…", systemImage: "sparkles")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let summary = model.importSummary {
                        Label(summary, systemImage: "checkmark.seal.fill")
                            .font(.caption)
                            .foregroundStyle(Theme.success)
                    }
                    Button {
                        Task { await model.generateCV() }
                    } label: {
                        Label("Generate my CV", systemImage: "doc.richtext")
                    }
                    .disabled(model.isImporting)
                } header: {
                    Text("Import evidence")
                } footer: {
                    Text(
                        "Skills read from a CV or your public repositories carry a citation and outrank self-reported ones."
                    )
                }

                Section("Engagement") {
                    HStack {
                        Text("Hourly rate")
                        Spacer()
                        TextField(
                            "e.g. 110", value: $model.draft.hourlyRate, format: .number
                        )
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.trailing)
                        .frame(width: 90)
                        Text(model.draft.currency).foregroundStyle(.secondary)
                    }
                    Stepper(
                        "\(model.draft.hoursPerWeek) hours/week",
                        value: $model.draft.hoursPerWeek, in: 4 ... 60, step: 4
                    )
                    Picker("Work style", selection: $model.draft.remotePreference) {
                        ForEach(RemotePreference.allCases, id: \.self) { Text($0.displayName) }
                    }
                    TextField("City", text: $model.draft.city)
                }

                Section {
                    Button {
                        Task { await model.save() }
                    } label: {
                        if model.isBusy { ProgressView() } else { Text("Save profile") }
                    }
                    .disabled(!model.canSave || model.isBusy)
                } footer: {
                    Text("Your profile powers the AI matching engine — richer profiles rank higher.")
                }

                PrivacySection(api: model.api, onDeleted: model.onSignOut)

                Section {
                    Button("Sign out", role: .destructive) { model.onSignOut() }
                }
            }
            .navigationTitle(model.user.fullName)
            .fileImporter(
                isPresented: $showingCVPicker,
                allowedContentTypes: [.pdf]
            ) { result in
                guard case let .success(url) = result else { return }
                Task {
                    // Security-scoped: files picked from outside the sandbox
                    // are unreadable without this bracket.
                    let scoped = url.startAccessingSecurityScopedResource()
                    defer { if scoped { url.stopAccessingSecurityScopedResource() } }
                    guard let data = try? Data(contentsOf: url) else {
                        model.errorMessage = "Could not read that file."
                        return
                    }
                    await model.importCV(pdfData: data, filename: url.lastPathComponent)
                }
            }
            .sheet(
                isPresented: .init(
                    get: { model.generatedCV != nil }, set: { if !$0 { model.generatedCV = nil } }
                )
            ) {
                if let cv = model.generatedCV {
                    NavigationStack {
                        ScrollView {
                            Text(cv.markdown)
                                .font(.system(.footnote, design: .monospaced))
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding()
                        }
                        .navigationTitle("Your CV")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .topBarLeading) {
                                Button("Done") { model.generatedCV = nil }
                            }
                            ToolbarItem(placement: .topBarTrailing) {
                                ShareLink(item: cv.markdown)
                            }
                        }
                    }
                }
            }
            .task { await model.load() }
            .sensoryFeedback(.success, trigger: model.savedBanner)
            .alert("Profile saved", isPresented: $model.savedBanner) {
                Button("OK", role: .cancel) {}
            } message: {
                Text("The matching engine re-indexed your profile.")
            }
        }
    }
}
