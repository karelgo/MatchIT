import Foundation

/// Presentation casing for technology names.
///
/// The matching engine lower-cases skills so they compare reliably, and `.capitalized`
/// then renders "Dbt", "Swiftui" and "Opentelemetry". To the technical audience this
/// app is built for that reads as careless, so known names get their real casing and
/// anything unrecognised falls back to per-word capitalisation.
enum SkillName {
    private static let canonical: [String: String] = [
        ".net": ".NET",
        "api": "API",
        "aws": "AWS",
        "azure": "Azure",
        "bi": "BI",
        "cd": "CD",
        "ci": "CI",
        "ci/cd": "CI/CD",
        "cicd": "CI/CD",
        "dbt": "dbt",
        "devops": "DevOps",
        "dotnet": ".NET",
        "elasticsearch": "Elasticsearch",
        "etl": "ETL",
        "gcp": "GCP",
        "gitops": "GitOps",
        "go": "Go",
        "golang": "Go",
        "graphql": "GraphQL",
        "grpc": "gRPC",
        "iac": "IaC",
        "ios": "iOS",
        "javascript": "JavaScript",
        "jvm": "JVM",
        "kubernetes": "Kubernetes",
        "llm": "LLM",
        "ml": "ML",
        "mysql": "MySQL",
        "node.js": "Node.js",
        "nodejs": "Node.js",
        "nosql": "NoSQL",
        "opentelemetry": "OpenTelemetry",
        "postgres": "Postgres",
        "postgresql": "PostgreSQL",
        "rest": "REST",
        "sql": "SQL",
        "sre": "SRE",
        "swiftui": "SwiftUI",
        "typescript": "TypeScript",
    ]

    /// Connectors stay lowercase unless they open the phrase, so "infrastructure as code"
    /// reads as "Infrastructure as Code" rather than title-cased like a headline.
    private static let connectors: Set<String> = [
        "a", "an", "and", "as", "at", "for", "in", "of", "on", "or", "the", "to", "with",
    ]

    /// Human-facing form of a raw skill or requirement string.
    static func display(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let known = canonical[trimmed.lowercased()] { return known }
        // Anything the source already cased deliberately is left alone.
        guard trimmed == trimmed.lowercased() else { return trimmed }
        return trimmed
            .split(separator: " ")
            .enumerated()
            .map { cased($0.element, isFirst: $0.offset == 0) }
            .joined(separator: " ")
    }

    /// Cases one word, preserving any wrapping punctuation so "(iac)" becomes "(IaC)".
    private static func cased(_ word: Substring, isFirst: Bool) -> String {
        let characters = Array(word)
        guard let start = characters.firstIndex(where: { $0.isLetter || $0.isNumber }),
              let end = characters.lastIndex(where: { $0.isLetter || $0.isNumber })
        else { return String(word) }

        let core = String(characters[start ... end])
        let replacement: String
        if let known = canonical[core.lowercased()] {
            replacement = known
        } else if !isFirst, connectors.contains(core.lowercased()) {
            replacement = core.lowercased()
        } else {
            replacement = core.capitalized
        }
        return String(characters[..<start]) + replacement + String(characters[(end + 1)...])
    }
}
