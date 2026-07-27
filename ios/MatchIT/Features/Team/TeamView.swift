import Observation
import SwiftUI

@MainActor
@Observable
final class TeamViewModel {
    let assignmentId: UUID
    var team: Team?
    var isBusy = false
    var errorMessage: String?

    private let api: APIClient

    init(api: APIClient, assignmentId: UUID) {
        self.api = api
        self.assignmentId = assignmentId
    }

    func build() async {
        isBusy = true
        defer { isBusy = false }
        do {
            team = try await api.buildTeam(assignmentId: assignmentId)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct TeamView: View {
    @State private var model: TeamViewModel

    init(api: APIClient, assignmentId: UUID) {
        _model = State(initialValue: TeamViewModel(api: api, assignmentId: assignmentId))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let message = model.errorMessage {
                    ErrorBanner(message: message)
                }
                if let team = model.team {
                    proposalCard(team)
                    ForEach(team.seats) { seat in
                        seatCard(seat)
                    }
                } else {
                    intro
                }
            }
            .padding(Theme.screenPadding)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Team")
        .navigationBarTitleDisplayMode(.inline)
        .task { if model.team == nil { await model.build() } }
    }

    private var intro: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Assemble a team", systemImage: "person.3.fill")
                .font(.system(.title3, design: .rounded, weight: .semibold))
            Text(
                "Each role is filled separately, so nobody is counted twice — and a seat is left open rather than filled by someone who can't do the job."
            )
            .font(.subheadline)
            .foregroundStyle(.secondary)
            if model.isBusy { ProgressView() }
        }
        .padding()
        .cardStyle()
    }

    private func proposalCard(_ team: Team) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Proposed team")
                    .font(.system(.title3, design: .rounded, weight: .semibold))
                Spacer()
                if team.unfilledSeats > 0 {
                    Text("\(team.unfilledSeats) open")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.orange.opacity(0.18), in: .capsule)
                        .foregroundStyle(.orange)
                }
            }
            Text(team.proposal.summary).font(.subheadline)

            bullets("Strengths", team.proposal.strengths, icon: "checkmark.circle.fill", tint: Theme.success)
            bullets("Gaps", team.proposal.gaps, icon: "exclamationmark.triangle.fill", tint: .orange)

            if !team.proposal.rationale.isEmpty {
                Divider()
                ForEach(team.proposal.rationale, id: \.self) { item in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(item.specialistHeadline) — \(item.roleTitle)")
                            .font(.caption.weight(.semibold))
                        Text(item.why).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding()
        .cardStyle()
    }

    private func seatCard(_ seat: TeamSeat) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(seat.roleTitle).font(.headline)
                    Text("\(seat.filled) of \(seat.seats) filled · \(seat.seniority.capitalized)")
                        .font(.caption)
                        .foregroundStyle(seat.isComplete ? Theme.success : .orange)
                }
                Spacer()
            }
            ChipFlow(items: seat.mustHaveSkills.map(\.capitalized))

            ForEach(seat.members, id: \.specialist.id) { member in
                HStack(spacing: 12) {
                    ScoreRing(score: member.score).frame(width: 42, height: 42)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(member.specialist.headline).font(.subheadline.weight(.medium))
                        Text("\(member.specialist.yearsExperience) yrs · \(member.specialist.country)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
            }

            if !seat.isComplete {
                Label(
                    "\(seat.seats - seat.filled) seat\(seat.seats - seat.filled == 1 ? "" : "s") still open",
                    systemImage: "person.badge.plus"
                )
                .font(.caption)
                .foregroundStyle(.orange)
            }
        }
        .padding()
        .cardStyle()
    }

    private func bullets(_ title: String, _ items: [String], icon: String, tint: Color) -> some View {
        Group {
            if !items.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title).font(.subheadline.weight(.semibold))
                    ForEach(items, id: \.self) { item in
                        Label(item, systemImage: icon)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .tint(tint)
                    }
                }
            }
        }
    }
}
