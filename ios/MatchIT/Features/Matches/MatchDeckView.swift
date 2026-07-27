import SwiftUI

struct MatchDeckView: View {
    @State private var model: MatchDeckViewModel
    @State private var dragOffset: CGSize = .zero
    @State private var interviewTarget: InterviewTarget?
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
        _model = State(initialValue: MatchDeckViewModel(api: api))
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                if let message = model.errorMessage {
                    ErrorBanner(message: message).padding(.horizontal)
                }
                content
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Opportunities")
            .task { await model.load() }
            .refreshable { await model.load() }
            .sensoryFeedback(.success, trigger: model.lastMutualMatch?.id)
            .sheet(item: $interviewTarget) { target in
                NavigationStack {
                    InterviewView(api: api, matchId: target.id, viewer: .specialist)
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if model.isLoading, model.deck.isEmpty {
            ProgressView("Finding opportunities…")
                .frame(maxHeight: .infinity)
        } else if model.deck.isEmpty {
            ContentUnavailableView(
                "You're all caught up",
                systemImage: "sparkles",
                description: Text("New opportunities appear here the moment the AI matches you.")
            )
        } else {
            deck
            actionBar
        }
    }

    private var deck: some View {
        ZStack {
            ForEach(Array(model.deck.prefix(3).enumerated().reversed()), id: \.element.id) { index, match in
                OpportunityCard(
                    match: match,
                    onInterview: index == 0 ? { interviewTarget = InterviewTarget(id: match.id) } : nil
                )
                .scaleEffect(1 - CGFloat(index) * 0.04)
                    .offset(y: CGFloat(index) * 12)
                    .offset(index == 0 ? dragOffset : .zero)
                    .rotationEffect(.degrees(index == 0 ? Double(dragOffset.width / 18) : 0))
                    .gesture(index == 0 ? dragGesture : nil)
                    .animation(.spring(duration: 0.35), value: dragOffset)
            }
        }
        .padding(.horizontal, Theme.screenPadding)
        .frame(maxHeight: .infinity)
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { dragOffset = $0.translation }
            .onEnded { value in
                let threshold: CGFloat = 110
                if value.translation.width > threshold {
                    swipe(.accepted)
                } else if value.translation.width < -threshold {
                    swipe(.rejected)
                } else {
                    dragOffset = .zero
                }
            }
    }

    private func swipe(_ decision: MatchDecision) {
        dragOffset = CGSize(width: decision == .accepted ? 600 : -600, height: 0)
        Task {
            await model.decideTopCard(decision)
            dragOffset = .zero
        }
    }

    private var actionBar: some View {
        HStack(spacing: 40) {
            Button {
                swipe(.rejected)
            } label: {
                Image(systemName: "xmark")
                    .font(.title2.weight(.bold))
                    .frame(width: 60, height: 60)
                    .background(.regularMaterial, in: .circle)
                    .foregroundStyle(Theme.danger)
            }
            .accessibilityLabel("Pass on this opportunity")

            Button {
                swipe(.accepted)
            } label: {
                Image(systemName: "checkmark")
                    .font(.title2.weight(.bold))
                    .frame(width: 60, height: 60)
                    .background(Theme.accent, in: .circle)
                    .foregroundStyle(.white)
            }
            .accessibilityLabel("Accept this opportunity")
        }
        .padding(.bottom, 24)
    }
}

/// `sheet(item:)` needs Identifiable, and UUID deliberately isn't — retroactively
/// conforming an imported type to an imported protocol is exactly what Swift 6
/// warns about, so wrap it instead.
struct InterviewTarget: Identifiable {
    let id: UUID
}

struct OpportunityCard: View {
    let match: Match
    var onInterview: (() -> Void)?

    private var requirements: AssignmentRequirements { match.assignment.requirements }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                if let role = requirements.roles.first {
                    Text(role.title)
                        .font(.system(.title2, design: .rounded, weight: .bold))
                }
                Spacer()
                ScoreRing(score: match.score).frame(width: 50, height: 50)
            }
            Text(requirements.summary)
                .font(.body)
                .foregroundStyle(.secondary)
                .lineLimit(6)

            if let role = requirements.roles.first {
                ChipFlow(items: role.mustHaveSkills.map(\.capitalized))
            }

            HStack(spacing: 14) {
                if let max = requirements.budget.maxHourly {
                    Label("≤ \(Int(max)) \(requirements.budget.currency)/h", systemImage: "eurosign.circle")
                }
                if let weeks = requirements.durationWeeks {
                    Label("\(weeks) weeks", systemImage: "calendar")
                }
                Label(
                    requirements.remoteAllowed ? "Remote OK" : "On-site",
                    systemImage: requirements.remoteAllowed ? "wifi" : "building.2"
                )
            }
            .font(.caption.weight(.medium))
            .foregroundStyle(.secondary)

            Spacer(minLength: 0)

            if let onInterview {
                Button(action: onInterview) {
                    Label("Take the AI interview", systemImage: "sparkles")
                        .font(.subheadline.weight(.medium))
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .tint(Theme.accent)
            }

            Label("Swipe right to accept, left to pass", systemImage: "hand.draw")
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .frame(maxWidth: .infinity, alignment: .center)
        }
        .padding(22)
        .frame(maxWidth: .infinity, minHeight: 420, alignment: .topLeading)
        .cardStyle()
        .accessibilityElement(children: .contain)
    }
}
