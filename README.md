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

The backend URL comes from the `MATCHIT_API_BASE_URL` build setting, resolved per
SDK in `ios/project.yml`: `localhost` for the simulator, and a `.local` Bonjour
hostname for device builds. The device value is machine-specific, so override it for
your own Mac — either in `project.yml` or per build:

```bash
xcodebuild -scheme MatchIT MATCHIT_API_BASE_URL=http://your-mac.local:8000/api/v1
```

A `.local` name is used rather than a bare IP because App Transport Security exempts
`.local` under `NSAllowsLocalNetworking`, but not private IP ranges. Remember to bind
the backend to `0.0.0.0` — a phone cannot reach a loopback-only server.

### Running on a physical device

There are two schemes, because signing differs:

| Scheme | Widget | Signing |
|---|---|---|
| `MatchIT` | yes | needs a **paid** Apple Developer Program membership |
| `MatchITFree` | no | works with a free Apple ID |

`MatchIT` shares an App Group between the app and its widget extension, and free
"personal team" provisioning cannot grant App Groups. `MatchITFree` builds the same
app without the widget target or that entitlement; `SharedStore` degrades to a no-op
when the App Group container is missing, so nothing else changes. Free provisioning
also expires every 7 days and needs a globally unique bundle id:

```bash
xcodebuild -scheme MatchITFree MATCHIT_FREE_BUNDLE_ID=com.yourname.matchit
```

On first launch the device refuses an app signed by a personal team until you trust
it under Settings → General → VPN & Device Management. iOS will also prompt for Local
Network access; declining it stops the app reaching your Mac.

## What is verified, and what is not

The backend is covered by **147 tests** (SQLite plus deterministic AI
fakes — no API keys, no external network), including a browser end-to-end test
that drives the admin portal with real Chromium. Two further tests guard risks
the rest of the suite structurally cannot see:

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

Fourteen iterations shipped — see [docs/roadmap.md](docs/roadmap.md) for what's next.

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
14. **Admin portal UI** — served by the API at `/admin-portal`, no dependencies,
    XSS-safe rendering, verified end to end in a real browser.
