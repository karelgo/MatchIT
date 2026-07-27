import Foundation
import Observation

@MainActor
@Observable
final class ProfileViewModel {
    var draft = SpecialistProfileDraft()
    var trustScore: Double?
    var newSkillName = ""
    var newSkillLevel = 7
    var isBusy = false
    var isLoaded = false
    var errorMessage: String?
    var savedBanner = false

    let api: APIClient
    let user: User
    let onSignOut: () -> Void

    init(api: APIClient, user: User, onSignOut: @escaping () -> Void) {
        self.api = api
        self.user = user
        self.onSignOut = onSignOut
    }

    func load() async {
        guard !isLoaded else { return }
        do {
            if let profile = try await api.mySpecialistProfile() {
                draft = SpecialistProfileDraft(
                    headline: profile.headline,
                    bio: profile.bio,
                    skills: profile.skills,
                    languages: profile.languages,
                    certifications: profile.certifications,
                    yearsExperience: profile.yearsExperience,
                    hourlyRate: profile.hourlyRate,
                    currency: profile.currency,
                    hoursPerWeek: profile.hoursPerWeek,
                    remotePreference: profile.remotePreference,
                    country: profile.country,
                    city: profile.city
                )
                trustScore = profile.trustScore
            }
            isLoaded = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func addSkill() {
        let name = newSkillName.trimmingCharacters(in: .whitespaces).lowercased()
        guard !name.isEmpty, !draft.skills.contains(where: { $0.name == name }) else { return }
        draft.skills.append(Skill(name: name, level: newSkillLevel, years: 0))
        newSkillName = ""
    }

    func removeSkill(_ skill: Skill) {
        draft.skills.removeAll { $0.name == skill.name }
    }

    var canSave: Bool {
        !draft.headline.trimmingCharacters(in: .whitespaces).isEmpty && !draft.skills.isEmpty
    }

    func save() async {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            let profile = try await api.upsertSpecialistProfile(draft)
            trustScore = profile.trustScore
            savedBanner = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
