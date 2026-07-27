import Foundation

/// What the home-screen widget shows. Written by the app, read by the widget
/// extension — widgets don't authenticate, so the app is the only network party.
struct WidgetSnapshot: Codable {
    var opportunityCount: Int
    var topOpportunityTitle: String?
    var topScore: Double?
    var updatedAt: Date

    static let empty = WidgetSnapshot(
        opportunityCount: 0, topOpportunityTitle: nil, topScore: nil, updatedAt: .distantPast
    )

    static let placeholder = WidgetSnapshot(
        opportunityCount: 3,
        topOpportunityTitle: "Microsoft Fabric Architect",
        topScore: 0.87,
        updatedAt: .now
    )
}

/// App-group-backed store shared between the app and the widget extension.
enum SharedStore {
    static let appGroupID = "group.com.matchit.app"
    static let widgetKind = "OpportunitiesWidget"

    private static var fileURL: URL? {
        FileManager.default
            .containerURL(forSecurityApplicationGroupIdentifier: appGroupID)?
            .appending(path: "widget-snapshot.json")
    }

    static func save(_ snapshot: WidgetSnapshot) {
        guard let url = fileURL, let data = try? JSONEncoder().encode(snapshot) else { return }
        try? data.write(to: url, options: .atomic)
    }

    static func load() -> WidgetSnapshot {
        guard let url = fileURL,
              let data = try? Data(contentsOf: url),
              let snapshot = try? JSONDecoder().decode(WidgetSnapshot.self, from: data)
        else { return .empty }
        return snapshot
    }
}
