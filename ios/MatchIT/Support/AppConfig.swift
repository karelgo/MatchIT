import Foundation

enum AppConfig {
    /// Backend base URL. Local development default; override per build
    /// configuration when staging/production environments exist.
    static let apiBaseURL = URL(string: "http://localhost:8000/api/v1")!
}
