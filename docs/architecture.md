# MatchIT — System Architecture

## Product thesis

MatchIT is **AI-first, not recruiter-first**. The unit of work is a *business
problem*, not a job posting. AI owns both sides of the funnel:

- **Demand side** — the AI Concierge turns a natural-language problem statement into
  a fully structured assignment (roles, skills, seniority, budget, timeline,
  languages, location policy).
- **Supply side** — AI builds a living understanding of each specialist from their
  CV, GitHub, certifications, portfolio and interviews, expressed as a skill graph
  and embeddings, not keywords.

Matching is therefore *understanding-to-understanding*, executed by the Matching
Engine in seconds.

## High-level topology

```
┌──────────────┐     HTTPS/JSON      ┌───────────────────────────────┐
│  iOS app     │◄───────────────────►│  FastAPI (app.matchit)        │
│  SwiftUI     │   WebSocket (chat)  │  ┌─────────┐ ┌─────────────┐  │
└──────────────┘                     │  │ API v1  │ │  Services   │  │
                                     │  └────┬────┘ └──────┬──────┘  │
┌──────────────┐                     │       │             │         │
│ Admin portal │◄───────────────────►│  ┌────▼─────────────▼──────┐  │
│ (web, later) │                     │  │ Domain (SQLAlchemy)     │  │
└──────────────┘                     │  └────┬───────┬──────┬─────┘  │
                                     └───────┼───────┼──────┼────────┘
                                      ┌──────▼──┐ ┌──▼───┐ ┌▼───────┐
                                      │Postgres │ │Redis │ │ Qdrant │
                                      └─────────┘ └──────┘ └────────┘
                                                     LLM / embedding providers
                                                     (Anthropic, OpenAI, Gemini,
                                                      Azure OpenAI — pluggable)
```

- **PostgreSQL** — system of record (users, profiles, assignments, matches,
  contracts, payments).
- **Redis** — session/cache, rate limiting, pub/sub for real-time chat and
  notification fan-out.
- **Qdrant** — vector database for semantic retrieval of specialists and
  assignments.
- **LLM providers** — abstracted behind `app.ai.llm.ChatModel`; provider choice is
  configuration, never code.

## Backend architecture

The backend is a modular monolith with strict internal layering — the right shape
until traffic proves where the seams are. Layers only depend downward:

```
app/api        HTTP endpoints, request/response schemas, auth dependencies
app/services   Use cases: AuthService, IntakeService, MatchingEngine, TrustScore
app/ai         Provider-agnostic AI: ChatModel, EmbeddingModel, prompts
app/models     SQLAlchemy domain entities
app/db         Engine, sessions, base classes
app/core       Settings, security primitives, logging
```

Rules:

1. **AI behind protocols.** Nothing outside `app/ai` imports a vendor SDK.
   `ChatModel` and `EmbeddingModel` are `Protocol`s with Anthropic/OpenAI
   implementations and deterministic fakes for tests.
2. **Services own transactions.** Endpoints are thin; a service method is a unit of
   work.
3. **Vector search behind `VectorIndex`.** Qdrant in production, an in-memory
   implementation in tests. Swapping vector DBs is a one-file change.
4. **Everything async.** SQLAlchemy async engine, httpx, async provider SDKs.

## Scaling path

| Stage | Change |
|---|---|
| Launch | Single FastAPI deployment, managed Postgres/Redis/Qdrant |
| Growth | Horizontal API replicas (stateless, JWT), read replicas, Redis cluster |
| Scale | Extract high-churn services first: matching workers (queue-driven), chat gateway (WebSocket), AI interview service. Kubernetes + Terraform (see `docs/roadmap.md`, Epic 10) |

Matching is embarrassingly parallel (per-assignment) and is the first candidate for
worker extraction: `POST /assignments/{id}/matches` already runs through a service
boundary that can be moved behind a queue without API changes.

## iOS architecture

- **Swift 6, SwiftUI, iOS 17+**, MVVM with the `@Observable` macro. We deliberately
  start with first-party frameworks only (no third-party dependencies): the app
  currently has zero package resolution risk, full Dynamic Type/Dark Mode support,
  and a design system in `ios/MatchIT/DesignSystem`. The Composable Architecture
  remains an option for feature modules once state complexity warrants it.
- **Networking** — `APIClient` (async/await) with automatic JWT refresh and typed
  endpoints mirroring the backend schemas.
- **Sessions** — tokens in Keychain; `SessionStore` drives root navigation
  (onboarding → auth → role-based home).
- Feature folders: `Auth`, `Concierge`, `Matches`, `Profile` — one view + one
  view model per screen, dependencies injected via `AppEnvironment`.

## Security posture

- Argon2id password hashing; JWT access tokens (15 min) + rotating refresh tokens
  (30 days) stored server-side as SHA-256 hashes and revoked on rotation/logout.
- Sign in with Apple: identity tokens verified against Apple's JWKS (issuer,
  audience, expiry) — no third-party auth dependency.
- Role-based access control (`freelancer`, `employee`, `consultancy`, `recruiter`,
  `hiring_manager`, `admin`) enforced in API dependencies.
- GDPR: data minimisation in AI prompts (profiles are projected to the fields the
  model needs), EU-region provider endpoints supported via configuration, deletion
  cascades wired at the schema level.
- Secrets only via environment (12-factor); `.env` files are git-ignored.
