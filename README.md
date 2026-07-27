# MatchIT — The AI Staffing Platform

MatchIT is an **AI-first staffing platform**: companies describe a business problem in
natural language, and AI does the rest — it understands the problem, writes the
assignment, finds and ranks specialists, interviews them, and generates the contract.
Hiring a highly skilled IT specialist should take minutes, not weeks.

Unlike marketplaces built around search, filters, and human recruiters (HeadFirst,
Malt, Upwork, LinkedIn), MatchIT's core loop is:

```
Company describes problem → AI Concierge extracts a structured assignment
→ Matching Engine ranks specialists (skills + semantics + constraints)
→ Mutual match → AI interview → Contract → Work starts
```

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI service: auth, profiles, AI intake, matching engine, vector search |
| `ios/` | Native SwiftUI app (Swift 6, MVVM + `@Observable`, iOS 17+) |
| `docs/` | Architecture, AI architecture, data model, roadmap (epics & stories) |
| `infra/` | docker-compose for local development (Postgres, Redis, Qdrant) |
| `web/` | Landing page, privacy policy and terms (static, self-contained) |
| `.github/workflows/` | CI: backend lint + tests, iOS build |

## Quickstart (backend)

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                      # fill in secrets for live AI providers
docker compose -f ../infra/docker-compose.yml up -d   # postgres, redis, qdrant
.venv/bin/alembic upgrade head
.venv/bin/uvicorn --factory app.main:create_app --reload
```

OpenAPI documentation is served at `http://localhost:8000/docs`.

Run the test suite (no external services or API keys required — tests use SQLite and
deterministic AI fakes):

```bash
cd backend && .venv/bin/pytest
```

## Quickstart (iOS)

The Xcode project is generated with [XcodeGen](https://github.com/yonaskolb/XcodeGen):

```bash
cd ios
xcodegen generate
open MatchIT.xcodeproj
```

Point the app at a running backend via the `API_BASE_URL` setting in
`ios/MatchIT/Support/AppConfig.swift`.

## What is verified, and what is not

The backend is covered by **145 offline tests** (SQLite plus deterministic AI
fakes — no API keys, no network). Two of those tests guard risks the rest of the
suite structurally cannot see:

- `test_migrations.py` compares the Postgres DDL that Alembic produces against
  the DDL the models produce, column by column. The suite builds its schema with
  `create_all`, so without this, migration drift would only surface in
  production.
- `test_ios_contract.py` parses `Models.swift` and checks every Swift DTO against
  a real API payload. CI cannot compile the iOS app, so a backend field going
  null under a non-optional Swift property would otherwise reach a user as a
  crash.

**Not verified here:** the Swift code is not compile-checked — there is no Swift
toolchain in the development container. The macOS CI job covers it and is
non-blocking until it has one green run. Two adapters raise rather than pretend:
`StripePaymentProvider` and `APNsSender` need real credentials; their protocols,
call sites and fakes are complete.

## Documentation

- [System architecture](docs/architecture.md)
- [AI architecture](docs/ai-architecture.md)
- [Data model](docs/data-model.md)
- [Roadmap — epics & user stories](docs/roadmap.md)

## Status

Thirteen iterations shipped — see [docs/roadmap.md](docs/roadmap.md) for what's next.

1. **Foundation** — auth (JWT + Apple), profiles, AI assignment intake, explainable
   matching engine, trust score, vector search, infrastructure and CI.
2. **Multi-turn concierge** — the assignment converges through dialogue; missing
   budget/duration are AI-estimated from EU market rates and flagged as estimates.
3. **Real-time chat** — a conversation opens on every mutual match, with REST
   history and WebSocket live delivery, plus the iOS Messages tab.
4. **AI interviews** — the agent interviews a candidate on exactly what their
   profile leaves unproven, scores the transcript against a rubric, and feeds the
   result into the trust score. The hiring manager sees risks and a
   recommendation; the specialist sees constructive feedback.
5. **Contracts** — an agent drafts the EU engagement contract from the agreed
   terms (never inventing them), both parties sign in-app, and the second
   signature activates it.
6. **Compliance** — rate limiting, an append-only audit trail, and GDPR export
   and erasure (refused while a contract is live).
7. **Team builder** — multi-role assignments are filled seat by seat, with open
   seats reported rather than padded.
8. **Evidence-backed skills** — CV and GitHub enrichment: every skill carries its
   source and the specific evidence behind it, and a stronger source is never
   overwritten by a weaker one.
9. **Admin & analytics** — funnel, conversion, quality signals, time-to-contract,
   per-feature AI usage, user suspension and audit search.
10. **Payments** — escrow-backed invoicing with EU VAT (domestic, reverse-charge,
    out-of-scope) and platform commission, in exact decimal arithmetic.
11. **Push notifications & infrastructure** — device registration and delivery on
    match/message/signature; Kubernetes manifests and EU-pinned Terraform.
12. **PDF CV upload & launch collateral** — CV import from PDF with honest
    failure messages; landing page, privacy/terms drafts, pitch deck, brand and
    App Store listing.
13. **Delight (Epic 9)** — home-screen widget, interview Live Activity with
    Dynamic Island, voice-first concierge dictation, AI-generated CVs from the
    evidence graph, and App Intents for Siri.
