import AppIntents

/// Siri / Shortcuts / Spotlight entry points. These open the app rather than
/// performing work headlessly: every surface behind them needs an
/// authenticated session and live data, which belongs in the app.
struct ShowOpportunitiesIntent: AppIntent {
    static let title: LocalizedStringResource = "Show Opportunities"
    static let description = IntentDescription("See the opportunities MatchIT has matched you with.")
    static let openAppWhenRun: Bool = true

    @MainActor
    func perform() async throws -> some IntentResult {
        .result()
    }
}

struct ShowMessagesIntent: AppIntent {
    static let title: LocalizedStringResource = "Show Messages"
    static let description = IntentDescription("Open your MatchIT conversations.")
    static let openAppWhenRun: Bool = true

    @MainActor
    func perform() async throws -> some IntentResult {
        .result()
    }
}

struct MatchITShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: ShowOpportunitiesIntent(),
            phrases: [
                "Show my \(.applicationName) opportunities",
                "Check \(.applicationName) matches",
            ],
            shortTitle: "Opportunities",
            systemImageName: "rectangle.stack.fill"
        )
        AppShortcut(
            intent: ShowMessagesIntent(),
            phrases: ["Show my \(.applicationName) messages"],
            shortTitle: "Messages",
            systemImageName: "bubble.left.and.bubble.right.fill"
        )
    }
}
