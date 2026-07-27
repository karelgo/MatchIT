import Foundation

enum APIError: LocalizedError {
    case unauthorized
    case server(status: Int, message: String)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .unauthorized: "Your session expired. Please sign in again."
        case let .server(_, message): message
        case .decoding: "Unexpected response from the server."
        }
    }
}

/// Async/await HTTP client with automatic refresh-token rotation.
actor APIClient {
    nonisolated let baseURL: URL
    private let session: URLSession
    private let tokenStore: KeychainTokenStore
    private var tokens: StoredTokens?

    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(baseURL: URL = AppConfig.apiBaseURL, tokenStore: KeychainTokenStore = KeychainTokenStore()) {
        self.baseURL = baseURL
        self.tokenStore = tokenStore
        self.session = URLSession(configuration: .default)
        self.tokens = tokenStore.load()

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .matchITTimestamp
        encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
    }

    var hasSession: Bool { tokens != nil }

    func adopt(_ response: TokenResponse) {
        let stored = StoredTokens(accessToken: response.accessToken, refreshToken: response.refreshToken)
        tokens = stored
        tokenStore.save(stored)
    }

    func signOut() async {
        if let refresh = tokens?.refreshToken {
            let body = ["refresh_token": refresh]
            _ = try? await send(path: "auth/logout", method: "POST", body: body, authorized: false) as Empty?
        }
        tokens = nil
        tokenStore.clear()
    }

    // MARK: - Typed endpoints

    func register(email: String, password: String, fullName: String, role: UserRole) async throws -> TokenResponse {
        let body = RegisterBody(email: email, password: password, fullName: fullName, role: role)
        let response: TokenResponse = try await post("auth/register", body: body, authorized: false)
        adopt(response)
        return response
    }

    func login(email: String, password: String) async throws -> TokenResponse {
        let response: TokenResponse = try await post(
            "auth/login", body: ["email": email, "password": password], authorized: false
        )
        adopt(response)
        return response
    }

    func me() async throws -> User {
        try await get("users/me")
    }

    func myCompanyProfile() async throws -> CompanyProfile? {
        do {
            return try await get("companies/me") as CompanyProfile
        } catch APIError.server(let status, _) where status == 404 {
            return nil
        }
    }

    func upsertCompanyProfile(name: String, industry: String, country: String) async throws -> CompanyProfile {
        try await put(
            "companies/me", body: ["name": name, "industry": industry, "country": country]
        )
    }

    func mySpecialistProfile() async throws -> SpecialistProfile? {
        do {
            return try await get("specialists/me") as SpecialistProfile
        } catch APIError.server(let status, _) where status == 404 {
            return nil
        }
    }

    func upsertSpecialistProfile(_ draft: SpecialistProfileDraft) async throws -> SpecialistProfile {
        try await put("specialists/me", body: draft)
    }

    func createAssignment(description: String) async throws -> Assignment {
        try await post("assignments", body: ["description": description])
    }

    func refineAssignment(assignmentId: UUID, answer: String) async throws -> Assignment {
        try await post(
            "assignments/\(assignmentId.uuidString.lowercased())/refine",
            body: ["answer": answer]
        )
    }

    func generateMatches(assignmentId: UUID) async throws -> [Match] {
        try await post("assignments/\(assignmentId.uuidString.lowercased())/matches", body: Empty())
    }

    func opportunityInbox() async throws -> [Match] {
        try await get("matches/inbox")
    }

    func decide(matchId: UUID, decision: MatchDecision) async throws -> Match {
        try await post(
            "matches/\(matchId.uuidString.lowercased())/decision",
            body: ["decision": decision.rawValue]
        )
    }

    func buildTeam(assignmentId: UUID) async throws -> Team {
        try await post("assignments/\(assignmentId.uuidString.lowercased())/team", body: Empty())
    }

    // MARK: - Profile enrichment

    func enrichFromCV(cvText: String) async throws -> EnrichmentResult {
        try await post("specialists/me/enrich/cv", body: ["cv_text": cvText])
    }

    func enrichFromGitHub(username: String) async throws -> EnrichmentResult {
        try await post("specialists/me/enrich/github", body: ["username": username])
    }

    // MARK: - Privacy (GDPR)

    /// Returns the export as pretty-printed JSON text — the shape is deliberately
    /// open-ended, so it is presented rather than decoded into a fixed model.
    func exportMyData() async throws -> String {
        var request = URLRequest(url: baseURL.appending(path: "users/me/export"))
        request.httpMethod = "GET"
        if let access = tokens?.accessToken {
            request.setValue("Bearer \(access)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await session.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw APIError.unauthorized }
        let object = try JSONSerialization.jsonObject(with: data)
        let pretty = try JSONSerialization.data(
            withJSONObject: object, options: [.prettyPrinted, .sortedKeys]
        )
        return String(decoding: pretty, as: UTF8.self)
    }

    func deleteMyAccount() async throws {
        _ = try await request(
            path: "users/me", method: "DELETE", bodyData: nil, authorized: true
        ) as Empty
        tokens = nil
        tokenStore.clear()
    }

    // MARK: - AI interview

    /// Returns nil when no interview has been started for this match yet.
    func interview(matchId: UUID) async throws -> Interview? {
        do {
            return try await get("matches/\(matchId.uuidString.lowercased())/interview") as Interview
        } catch APIError.server(let status, _) where status == 404 {
            return nil
        }
    }

    func startInterview(matchId: UUID) async throws -> Interview {
        try await post("matches/\(matchId.uuidString.lowercased())/interview", body: Empty())
    }

    func answerInterview(matchId: UUID, answer: String) async throws -> Interview {
        try await post(
            "matches/\(matchId.uuidString.lowercased())/interview/answer",
            body: ["answer": answer]
        )
    }

    // MARK: - Contracts

    func contract(matchId: UUID) async throws -> Contract? {
        do {
            return try await get("matches/\(matchId.uuidString.lowercased())/contract") as Contract
        } catch APIError.server(let status, _) where status == 404 {
            return nil
        }
    }

    func createContract(
        matchId: UUID,
        hourlyRate: Double,
        currency: String,
        hoursPerWeek: Int,
        startDate: String,
        endDate: String?
    ) async throws -> Contract {
        struct Body: Encodable {
            let hourlyRate: Double
            let currency: String
            let hoursPerWeek: Int
            let startDate: String
            let endDate: String?
        }
        return try await post(
            "matches/\(matchId.uuidString.lowercased())/contract",
            body: Body(
                hourlyRate: hourlyRate,
                currency: currency,
                hoursPerWeek: hoursPerWeek,
                startDate: startDate,
                endDate: endDate
            )
        )
    }

    func signContract(matchId: UUID) async throws -> Contract {
        try await post("matches/\(matchId.uuidString.lowercased())/contract/sign", body: Empty())
    }

    // MARK: - Chat

    func conversations() async throws -> [Conversation] {
        try await get("conversations")
    }

    func messages(conversationId: UUID) async throws -> [ChatMessage] {
        try await get("conversations/\(conversationId.uuidString.lowercased())/messages")
    }

    func sendMessage(conversationId: UUID, content: String) async throws -> ChatMessage {
        try await post(
            "conversations/\(conversationId.uuidString.lowercased())/messages",
            body: ["content": content]
        )
    }

    /// Live-chat socket URL. Refreshes the session first so the token embedded in
    /// the query string is not about to expire mid-connection.
    func chatSocketURL(conversationId: UUID) async throws -> URL {
        if tokens == nil { throw APIError.unauthorized }
        try await refreshSession()
        guard let access = tokens?.accessToken,
              var components = URLComponents(
                  url: baseURL.appending(
                      path: "ws/conversations/\(conversationId.uuidString.lowercased())"
                  ),
                  resolvingAgainstBaseURL: false
              )
        else { throw APIError.unauthorized }
        components.scheme = components.scheme == "https" ? "wss" : "ws"
        components.queryItems = [URLQueryItem(name: "token", value: access)]
        guard let url = components.url else { throw APIError.unauthorized }
        return url
    }

    // MARK: - Transport

    private struct Empty: Codable {}

    private struct RegisterBody: Encodable {
        let email: String
        let password: String
        let fullName: String
        let role: UserRole
    }

    private struct ServerError: Decodable {
        let detail: String?
    }

    private func get<Out: Decodable>(_ path: String) async throws -> Out {
        try await request(path: path, method: "GET", bodyData: nil, authorized: true)
    }

    private func post<In: Encodable, Out: Decodable>(
        _ path: String, body: In, authorized: Bool = true
    ) async throws -> Out {
        try await request(
            path: path, method: "POST", bodyData: try encoder.encode(body), authorized: authorized
        )
    }

    private func put<In: Encodable, Out: Decodable>(_ path: String, body: In) async throws -> Out {
        try await request(path: path, method: "PUT", bodyData: try encoder.encode(body), authorized: true)
    }

    private func send<Out: Decodable>(
        path: String, method: String, body: some Encodable, authorized: Bool
    ) async throws -> Out {
        try await request(
            path: path, method: method, bodyData: try encoder.encode(body), authorized: authorized
        )
    }

    private func request<Out: Decodable>(
        path: String, method: String, bodyData: Data?, authorized: Bool, isRetry: Bool = false
    ) async throws -> Out {
        var urlRequest = URLRequest(url: baseURL.appending(path: path))
        urlRequest.httpMethod = method
        urlRequest.httpBody = bodyData
        if bodyData != nil {
            urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if authorized, let access = tokens?.accessToken {
            urlRequest.setValue("Bearer \(access)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await session.data(for: urlRequest)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0

        if status == 401, authorized, !isRetry {
            try await refreshSession()
            return try await request(
                path: path, method: method, bodyData: bodyData, authorized: authorized, isRetry: true
            )
        }
        guard (200 ..< 300).contains(status) else {
            if status == 401 { throw APIError.unauthorized }
            let detail = (try? decoder.decode(ServerError.self, from: data))?.detail
            throw APIError.server(status: status, message: detail ?? "Request failed (\(status)).")
        }
        if Out.self == Empty.self, data.isEmpty {
            return Empty() as! Out
        }
        do {
            return try decoder.decode(Out.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    private func refreshSession() async throws {
        guard let refresh = tokens?.refreshToken else { throw APIError.unauthorized }
        var urlRequest = URLRequest(url: baseURL.appending(path: "auth/refresh"))
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try encoder.encode(["refresh_token": refresh])
        let (data, response) = try await session.data(for: urlRequest)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            tokens = nil
            tokenStore.clear()
            throw APIError.unauthorized
        }
        adopt(try decoder.decode(TokenResponse.self, from: data))
    }
}
