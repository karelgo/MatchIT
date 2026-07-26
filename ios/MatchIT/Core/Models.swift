import Foundation

// DTOs mirroring the backend API (snake_case JSON, decoded via .convertFromSnakeCase).

enum UserRole: String, Codable, CaseIterable, Sendable {
    case freelancer
    case employee
    case consultancy
    case recruiter
    case hiringManager = "hiring_manager"
    case admin

    var isSpecialist: Bool {
        switch self {
        case .freelancer, .employee, .consultancy: true
        case .recruiter, .hiringManager, .admin: false
        }
    }

    var displayName: String {
        switch self {
        case .freelancer: "Freelancer"
        case .employee: "Employee"
        case .consultancy: "Consultancy"
        case .recruiter: "Recruiter"
        case .hiringManager: "Hiring Manager"
        case .admin: "Admin"
        }
    }
}

struct User: Codable, Identifiable, Sendable, Equatable {
    let id: UUID
    let email: String
    let fullName: String
    let role: UserRole
    let isVerified: Bool
}

struct TokenResponse: Codable, Sendable {
    let accessToken: String
    let refreshToken: String
    let user: User
}

struct Skill: Codable, Identifiable, Sendable, Equatable, Hashable {
    var name: String
    var level: Int
    var years: Double

    var id: String { name }
}

enum RemotePreference: String, Codable, CaseIterable, Sendable {
    case remote, hybrid, onsite

    var displayName: String { rawValue.capitalized }
}

struct SpecialistProfile: Codable, Identifiable, Sendable {
    let id: UUID
    let userId: UUID
    var headline: String
    var bio: String
    var skills: [Skill]
    var languages: [String]
    var certifications: [String]
    var yearsExperience: Int
    var hourlyRate: Double?
    var currency: String
    var hoursPerWeek: Int
    var remotePreference: RemotePreference
    var country: String
    var city: String
    var trustScore: Double
}

struct SpecialistProfileDraft: Codable, Sendable {
    var headline = ""
    var bio = ""
    var skills: [Skill] = []
    var languages: [String] = []
    var certifications: [String] = []
    var yearsExperience = 0
    var hourlyRate: Double?
    var currency = "EUR"
    var hoursPerWeek = 40
    var remotePreference = RemotePreference.remote
    var country = "NL"
    var city = ""
}

struct CompanyProfile: Codable, Identifiable, Sendable {
    let id: UUID
    let userId: UUID
    var name: String
    var industry: String
    var country: String
    var isVerified: Bool
}

struct RoleRequirement: Codable, Sendable, Hashable {
    let title: String
    let count: Int
    let seniority: String
    let mustHaveSkills: [String]
    let niceToHaveSkills: [String]
}

struct BudgetRange: Codable, Sendable, Hashable {
    let minHourly: Double?
    let maxHourly: Double?
    let currency: String
}

struct AssignmentRequirements: Codable, Sendable, Hashable {
    let summary: String
    let roles: [RoleRequirement]
    let languages: [String]
    let country: String?
    let remoteAllowed: Bool
    let durationWeeks: Int?
    let durationIsEstimated: Bool
    let budget: BudgetRange
    let budgetIsEstimated: Bool
    let clarifyingQuestions: [String]
}

struct IntakeMessage: Codable, Sendable, Hashable {
    let role: String
    let content: String

    var isCompany: Bool { role == "company" }
}

struct Assignment: Codable, Identifiable, Sendable {
    let id: UUID
    let rawDescription: String
    let requirements: AssignmentRequirements
    let intakeHistory: [IntakeMessage]
    let status: String
}

enum MatchDecision: String, Codable, Sendable {
    case pending, accepted, rejected
}

struct MatchSpecialistView: Codable, Sendable, Identifiable {
    let id: UUID
    let headline: String
    let skills: [Skill]
    let yearsExperience: Int
    let hourlyRate: Double?
    let currency: String
    let country: String
    let remotePreference: RemotePreference
    let trustScore: Double
}

struct AssignmentBrief: Codable, Sendable, Identifiable {
    let id: UUID
    let requirements: AssignmentRequirements
    let status: String
}

struct Match: Codable, Identifiable, Sendable {
    let id: UUID
    let assignmentId: UUID
    let specialistId: UUID
    let score: Double
    let breakdown: [String: Double]
    let companyDecision: MatchDecision
    let specialistDecision: MatchDecision
    let status: String
    let specialist: MatchSpecialistView
    let assignment: AssignmentBrief
}
