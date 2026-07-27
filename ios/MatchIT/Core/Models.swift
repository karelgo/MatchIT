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
    /// Provenance: self_reported, cv, github, certification or interview.
    /// Optional so profile drafts, which never set it, still encode.
    var source: String?
    var evidence: String?

    var id: String { name }
    var isEvidenced: Bool { (source ?? "self_reported") != "self_reported" }
}

struct EnrichmentResult: Codable, Sendable {
    let source: String
    let summary: String
    let skillsAdded: Int
    let skillsUpdated: Int
    let evidenceCount: Int
    let profile: SpecialistProfile
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

struct Assignment: Codable, Identifiable, Sendable, Equatable {
    let id: UUID
    let rawDescription: String
    let requirements: AssignmentRequirements
    let intakeHistory: [IntakeMessage]
    let status: String
}

enum MatchDecision: String, Codable, Sendable {
    case pending, accepted, rejected
}

struct MatchSpecialistView: Codable, Sendable, Identifiable, Equatable {
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

struct AssignmentBrief: Codable, Sendable, Identifiable, Equatable {
    let id: UUID
    let requirements: AssignmentRequirements
    let status: String
}

struct Match: Codable, Identifiable, Sendable, Equatable {
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

struct InterviewQuestion: Codable, Sendable, Hashable {
    let question: String
    let skill: String
    let rationale: String
}

struct TranscriptEntry: Codable, Sendable, Hashable {
    let question: String
    let answer: String
}

struct AnswerScore: Codable, Sendable, Hashable {
    let question: String
    let score: Double
    let reasoning: String
}

/// Server-projected: `concerns`, `recommendation`, `summary` and `perQuestion`
/// are present only for the hiring manager.
struct InterviewAssessment: Codable, Sendable, Hashable {
    let overallScore: Double
    let strengths: [String]
    let developmentAreas: [String]
    let concerns: [String]?
    let recommendation: String?
    let summary: String?
    let perQuestion: [AnswerScore]?
}

struct Interview: Codable, Identifiable, Sendable {
    let id: UUID
    let matchId: UUID
    let status: String
    let gapSummary: String
    let questions: [InterviewQuestion]
    let transcript: [TranscriptEntry]
    let currentQuestion: InterviewQuestion?
    let answeredCount: Int
    let totalQuestions: Int
    let assessment: InterviewAssessment?

    var isComplete: Bool { status == "completed" }
    var progress: Double {
        totalQuestions == 0 ? 0 : Double(answeredCount) / Double(totalQuestions)
    }
}

struct CVSection: Codable, Sendable, Hashable {
    let heading: String
    let bullets: [String]
}

struct GeneratedCV: Codable, Sendable {
    let headline: String
    let summary: String
    let sections: [CVSection]
    let markdown: String
}

struct TeamMember: Codable, Sendable {
    let specialist: MatchSpecialistView
    let score: Double
    let breakdown: [String: Double]
}

struct TeamSeat: Codable, Sendable, Identifiable {
    let roleTitle: String
    let seniority: String
    let seats: Int
    let filled: Int
    let mustHaveSkills: [String]
    let members: [TeamMember]

    var id: String { roleTitle }
    var isComplete: Bool { filled >= seats }
}

struct TeamRationale: Codable, Sendable, Hashable {
    let roleTitle: String
    let specialistHeadline: String
    let why: String
}

struct TeamProposal: Codable, Sendable {
    let summary: String
    let strengths: [String]
    let gaps: [String]
    let rationale: [TeamRationale]
}

struct Team: Codable, Sendable {
    let assignmentId: UUID
    let seats: [TeamSeat]
    let unfilledSeats: Int
    let proposal: TeamProposal
}

struct ContractClause: Codable, Sendable, Hashable {
    let heading: String
    let body: String
}

struct ContractDraft: Codable, Sendable, Hashable {
    let title: String
    let scopeOfWork: [String]
    let rateTerms: String
    let durationTerms: String
    let clauses: [ContractClause]
    let governingLaw: String
    let openPoints: [String]
}

struct Contract: Codable, Identifiable, Sendable {
    let id: UUID
    let matchId: UUID
    let status: String
    let hourlyRate: Double
    let currency: String
    let hoursPerWeek: Int
    let startDate: String
    let endDate: String?
    let draft: ContractDraft
    let companySigned: Bool
    let specialistSigned: Bool
    let signedByMe: Bool

    var isActive: Bool { status == "active" }
    var awaitingMySignature: Bool { !signedByMe && !isActive }
}

struct Conversation: Codable, Identifiable, Sendable, Hashable {
    let id: UUID
    let matchId: UUID
    let counterpartName: String
    let assignmentTitle: String
    let lastMessage: String?
    let lastMessageAt: Date?
}

struct ChatMessage: Codable, Identifiable, Sendable, Hashable {
    let id: UUID
    let conversationId: UUID
    let senderId: UUID
    let senderName: String
    let content: String
    let createdAt: Date
}
