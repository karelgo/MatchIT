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

## Documentation

- [System architecture](docs/architecture.md)
- [AI architecture](docs/ai-architecture.md)
- [Data model](docs/data-model.md)
- [Roadmap — epics & user stories](docs/roadmap.md)

## Status

Iteration 1 (Foundation) is complete: architecture, backend core (auth, profiles,
AI assignment intake, matching engine, trust score, vector search), iOS app
foundation (design system, auth, concierge intake, match deck), infrastructure and
CI. See [docs/roadmap.md](docs/roadmap.md) for what ships next.
