import SwiftUI

/// MatchIT design language: calm surfaces, one confident accent, generous space.
enum Theme {
    static let accent = Color(red: 0.29, green: 0.33, blue: 0.95)
    static let accentSoft = Color(red: 0.29, green: 0.33, blue: 0.95).opacity(0.12)
    static let success = Color(red: 0.16, green: 0.66, blue: 0.43)
    static let danger = Color(red: 0.87, green: 0.26, blue: 0.32)

    static let cardCornerRadius: CGFloat = 20
    static let screenPadding: CGFloat = 20

    static func title(_ text: String) -> Text {
        Text(text).font(.system(.largeTitle, design: .rounded, weight: .bold))
    }
}

/// Large soft card used across decks and forms.
struct CardBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(.regularMaterial, in: .rect(cornerRadius: Theme.cardCornerRadius))
            .shadow(color: .black.opacity(0.08), radius: 14, y: 6)
    }
}

extension View {
    func cardStyle() -> some View { modifier(CardBackground()) }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.headline, design: .rounded))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 15)
            .background(Theme.accent, in: .rect(cornerRadius: 14))
            .foregroundStyle(.white)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.99 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

extension ButtonStyle where Self == PrimaryButtonStyle {
    static var primary: PrimaryButtonStyle { PrimaryButtonStyle() }
}
