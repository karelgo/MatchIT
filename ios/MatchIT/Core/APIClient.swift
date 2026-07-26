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
    private let baseURL: URL
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
        decoder.dateDecodingStrategy = .iso8601
        encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
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
