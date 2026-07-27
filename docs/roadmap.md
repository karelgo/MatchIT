# MatchIT — Roadmap: Epics & User Stories

Build order optimises for the core loop first: *describe problem → structured
assignment → ranked specialists → mutual match*. Everything else compounds on it.

## Epic 1 — Platform foundation ✅ (Iteration 1, this release)

- ✅ As a user I can register with email/password or Sign in with Apple and stay
  signed in securely (JWT + rotating refresh tokens, Argon2id, Apple JWKS
  verification).
- ✅ As a specialist I can create a rich profile (skills with levels, rate,
  availability, languages, location, remote preference, links).
- ✅ As a hiring manager I can create a company profile.
- ✅ As a hiring manager I can describe my problem in natural language and the AI
  extracts a complete structured assignment, including clarifying questions.
- ✅ As a hiring manager I get ranked specialists with an explainable score
  breakdown (skills, semantics, rate, availability, location, language).
- ✅ As either side I can accept/reject a match; mutual acceptance is detected.
- ✅ Trust score computed with a persisted factor breakdown.
- ✅ Infrastructure: Docker, docker-compose (Postgres/Redis/Qdrant), Alembic
  migrations, GitHub Actions CI, deterministic offline test suite.
- ✅ iOS foundation: design system, auth, concierge intake flow, match deck
  (swipe), profile — Swift 6, MVVM/@Observable, no third-party dependencies.

## Epic 2 — Conversational concierge & realtime chat
- ✅ Multi-turn concierge (Iteration 2): answers to clarifying questions are fed
  back into extraction over the full transcript (`POST /assignments/{id}/refine`),
  the dialogue is persisted per assignment, and missing budget/duration are
  AI-estimated from EU market rates and flagged as estimates.
- ✅ Real-time chat on mutual match (Iteration 3): a conversation opens
  automatically when both sides accept; REST history + WebSocket live delivery
  fanned out over `PubSub` (Redis in production), with the iOS Messages tab.
- Team composition proposals from the concierge.
- AI assistant in thread, code snippets & diagram attachments.
- Push notifications (APNs): new matches, messages, availability requests.

## Epic 3 — Supply-side intelligence
- CV/PDF parsing into the skill graph; GitHub repository analysis; certification
  validation; AI-generated profile summaries & video-intro transcription.
- Identity verification flow; trust score factors go evidence-based.

## Epic 4 — Matching v2
- Persisted assignment embeddings, LLM re-rank stage with rationale, feedback loop
  from match decisions into ranking weights, team-builder agent (multi-role
  assignments assembled as complementary teams).

## Epic 5 — AI interviews
- ✅ Interview agent (Iteration 4): questions generated from the assignment plus a
  profile gap analysis, answered in-app, scored against a rubric, with a
  hiring-manager summary and a specialist-safe projection. Feeds the trust score.
- In-app video interviews + transcription, reusing the same assess step.
- Re-interviewing when an assignment materially changes.

## Epic 6 — Contracts & payments
- ✅ Contract generator agent (Iteration 5): drafts an EU engagement contract from
  the assignment plus the agreed commercial terms — the model never invents a rate
  or date, and anything contentious lands in `open_points` for a lawyer. Both
  parties sign in-app; the second signature activates the contract.
- Stripe Connect: escrow, hourly & fixed-price, invoicing with VAT, subscriptions
  & commission.

## Epic 7 — Admin portal & analytics
- User management, disputes, fraud queue; funnel/retention/LTV/CAC dashboards;
  AI cost per feature; revenue reporting.

## Epic 8 — Trust & safety, compliance
- ✅ Rate limiting (Iteration 6): fixed-window, Redis-backed so the budget is
  shared across replicas, on registration and login.
- ✅ Append-only audit log: registration, login success/failure, exports and
  erasures. The actor FK is SET NULL on delete, never CASCADE — erasing an
  account must not erase the evidence of what it did.
- ✅ GDPR data-subject tooling: Article 15/20 export and Article 17 erasure,
  refused while a contract is active (Art. 17(3)).
- SOC2 controls, anomaly detection, admin-facing audit search.

## Epic 9 — Delight
- Widgets & Live Activities (interview countdowns, match alerts), voice-first
  concierge, Apple Intelligence integration, AI-generated portfolios/CVs.

## Epic 10 — Scale-out
- Kubernetes + Terraform (EKS/AKS), matching workers behind a queue, chat gateway
  extraction, multi-region EU data residency, enterprise white-label.

## Next up (recommended)

**Epic 4 — matching v2 (team builder).** The concierge already extracts multi-role
assignments (`2× Fabric architect`), but the engine ranks individuals and ignores
`count` entirely — a company asking for a team gets a list. A team-builder agent
that assembles complementary specialists against a multi-role assignment is the
most visible remaining gap between what intake promises and what matching
delivers.
