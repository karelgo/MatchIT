import Foundation

enum AppConfig {
    /// Backend base URL, supplied by the `MATCHIT_API_BASE_URL` build setting via
    /// Info.plist so that simulator builds reach localhost while device builds reach
    /// a backend on the LAN. See `ios/project.yml`.
    static let apiBaseURL: URL = {
        let value = Bundle.main.object(forInfoDictionaryKey: "APIBaseURL") as? String ?? ""
        // A nil scheme means the build setting never expanded, which would otherwise
        // fail later as confusing network errors rather than as a build misconfiguration.
        guard let url = URL(string: value), url.scheme != nil else {
            fatalError("APIBaseURL is missing or malformed (\(value.isEmpty ? "unset" : value))")
        }
        return url
    }()
}
