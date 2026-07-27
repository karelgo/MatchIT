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

    /// Which way the current drag is leaning, so the card can say what will happen
    /// before the gesture completes.
    private var dragDecision: MatchDecision? {
        if dragOffset.width > 24 { return .accepted }
        if dragOffset.width < -24 { return .rejected }
        return nil
    }

    private var dragProgress: Double {
        min(1, abs(dragOffset.width) / 110)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                if let message = model.errorMessage {
                    ErrorBanner(
                        message: message,
                        onRetry: { Task { await model.load() } },
                        onDismiss: { model.errorMessage = nil }
                    )
                    .padding(.horizontal)
                }
                content
                // In normal layout flow rather than a `safeAreaInset`: an inset whose
                // content starts out empty does not reliably lay out when it appears,
                // and this needs to reserve space instead of covering the action bar.
                undoBar
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Opportunities")
            .task { await model.load() }
            .refreshable { await model.load() }
            .sensoryFeedback(.success, trigger: model.lastMutualMatch?.id)
            .animation(.spring(duration: 0.3), value: model.pendingUndo?.id)
            // A held decision must not be lost just because the screen went away.
            .onDisappear { model.flushPendingDecision() }
            .sheet(item: activeSheetBinding) { sheet in
                switch sheet {
                case let .interview(matchId):
                    NavigationStack {
                        InterviewView(api: api, matchId: matchId, viewer: .specialist)
                    }
                case let .mutualMatch(match):
                    MutualMatchSheet(match: match) { model.lastMutualMatch = nil }
                }
            }
        }
    }

    /// Interviews and mutual matches share one sheet.
    ///
    /// A held decision can commit into a mutual match while the interview sheet is
    /// already open, and two `.sheet` modifiers on the same view then race to present.
    /// Routing both through a single binding makes that defined, and the match wins
    /// because it is the more consequential event.
    private enum DeckSheet: Identifiable {
        case interview(UUID)
        case mutualMatch(Match)

        var id: String {
            switch self {
            case let .interview(matchId): "interview-\(matchId)"
            case let .mutualMatch(match): "mutual-\(match.id)"
            }
        }
    }

    private var activeSheetBinding: Binding<DeckSheet?> {
        Binding(
            get: {
                if let match = model.lastMutualMatch { return .mutualMatch(match) }
                if let target = interviewTarget { return .interview(target.id) }
                return nil
            },
            set: { newValue in
                guard newValue == nil else { return }
                model.lastMutualMatch = nil
                interviewTarget = nil
            }
        )
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

    @ViewBuilder
    private var undoBar: some View {
        if let pending = model.pendingUndo {
            HStack(spacing: 12) {
                Text(pending.summary)
                    .font(.subheadline)
                    .lineLimit(1)
                Spacer()
                Button("Undo") { model.undo() }
                    .font(.subheadline.weight(.semibold))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Theme.cardSurface, in: .capsule)
            .shadow(color: .black.opacity(0.08), radius: 8, y: 3)
            .padding(.horizontal, Theme.screenPadding)
            .padding(.bottom, 8)
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }

    private var deck: some View {
        ZStack {
            ForEach(Array(model.deck.prefix(3).enumerated().reversed()), id: \.element.id) { index, match in
                OpportunityCard(
                    match: match,
                    onInterview: index == 0 ? { interviewTarget = InterviewTarget(id: match.id) } : nil,
                    dragDecision: index == 0 ? dragDecision : nil,
                    dragProgress: index == 0 ? dragProgress : 0
                )
                .scaleEffect(1 - CGFloat(index) * 0.04)
                .offset(y: CGFloat(index) * 12)
                .offset(index == 0 ? dragOffset : .zero)
                .rotationEffect(.degrees(index == 0 ? Double(dragOffset.width / 18) : 0))
                .gesture(index == 0 ? dragGesture : nil)
                .animation(.spring(duration: 0.35), value: dragOffset)
                .accessibilityActions {
                    Button("Accept this opportunity") { swipe(.accepted) }
                    Button("Pass on this opportunity") { swipe(.rejected) }
                }
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
        // Let the card fly off before it is removed, otherwise the offset lands on the
        // next card instead and nothing appears to move.
        Task {
            try? await Task.sleep(for: .milliseconds(220))
            model.decideTopCard(decision)
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
        .padding(.bottom, 8)
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
    var dragDecision: MatchDecision?
    var dragProgress: Double = 0

    @State private var showsDetail = false
    /// Keeps the stacked cards a consistent size while still growing with text size —
    /// the previous hard 420pt clipped its content at large accessibility sizes.
    @ScaledMetric(relativeTo: .body) private var minCardHeight: CGFloat = 420

    private var requirements: AssignmentRequirements { match.assignment.requirements }
    private var quality: MatchQuality { MatchQuality(score: match.score) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    if let role = requirements.roles.first {
                        Text(role.title)
                            .font(.system(.title2, design: .rounded, weight: .bold))
                    }
                    MatchQualityBadge(quality: quality)
                }
                Spacer()
                ScoreRing(score: match.score)
            }
            Text(requirements.summary)
                .font(.body)
                .foregroundStyle(.secondary)
                .lineLimit(6)

            if let role = requirements.roles.first {
                ChipFlow(items: role.mustHaveSkills.map(SkillName.display))
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

            // A sheet rather than inline expansion: this card is a fixed-size draggable
            // object, and growing it in place crushes the title and summary to one line
            // and clips the bottom.
            Button {
                showsDetail = true
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "chart.bar.xaxis")
                    Text("Why this match")
                    Image(systemName: "chevron.right")
                        .font(.caption2.weight(.semibold))
                }
                .font(.footnote.weight(.medium))
            }
            .buttonStyle(.plain)

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
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)
        }
        .padding(22)
        .frame(maxWidth: .infinity, minHeight: minCardHeight, alignment: .topLeading)
        .cardStyle()
        .overlay(alignment: .top) { dragStamp }
        .accessibilityElement(children: .contain)
        .sheet(isPresented: $showsDetail) {
            OpportunityDetailSheet(match: match)
        }
    }

    /// Tells the user what the in-flight gesture will do, and when it has gone far enough.
    @ViewBuilder
    private var dragStamp: some View {
        if let dragDecision {
            let accepted = dragDecision == .accepted
            Label(
                accepted ? "Accept" : "Pass",
                systemImage: accepted ? "checkmark.circle.fill" : "xmark.circle.fill"
            )
            .font(.system(.title3, design: .rounded, weight: .heavy))
            .foregroundStyle(accepted ? Theme.success : Theme.danger)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(.regularMaterial, in: .capsule)
            .overlay {
                Capsule().stroke(accepted ? Theme.success : Theme.danger, lineWidth: 2)
            }
            .opacity(dragProgress)
            .scaleEffect(0.85 + 0.15 * dragProgress)
            .padding(.top, 18)
            .accessibilityHidden(true)
        }
    }
}
