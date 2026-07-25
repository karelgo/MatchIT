import SwiftUI

@main
struct MatchITApp: App {
    private let api = APIClient()

    var body: some Scene {
        WindowGroup {
            RootView(api: api)
        }
    }
}
