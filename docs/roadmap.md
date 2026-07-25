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
- Multi-turn concierge: answers to clarifying questions refine the assignment;
  budget & duration estimation; team composition proposals.
- Real-time chat on mutual match (WebSocket + Redis pub/sub), AI assistant in
  thread, code snippets & diagram attachments.
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
- Interview agent: question generation from the assignment + profile gap analysis,
  in-app video interviews, transcription, scoring rubric, structured summaries
  for the hiring manager.

## Epic 6 — Contracts & payments
- Contract generator agent (assignment + match + rates → draft contract, EU
  jurisdictions), e-signature, Stripe Connect: escrow, hourly & fixed-price,
  invoicing with VAT, subscriptions & commission.

## Epic 7 — Admin portal & analytics
- User management, disputes, fraud queue; funnel/retention/LTV/CAC dashboards;
  AI cost per feature; revenue reporting.

## Epic 8 — Trust & safety, compliance
- SOC2 controls, audit log everywhere, rate limiting, anomaly detection,
  GDPR data-subject tooling (export, delete).

## Epic 9 — Delight
- Widgets & Live Activities (interview countdowns, match alerts), voice-first
  concierge, Apple Intelligence integration, AI-generated portfolios/CVs.

## Epic 10 — Scale-out
- Kubernetes + Terraform (EKS/AKS), matching workers behind a queue, chat gateway
  extraction, multi-region EU data residency, enterprise white-label.

## Next up (recommended)

**Epic 2, story 1 — multi-turn concierge refinement.** The intake service already
returns `clarifying_questions`; the next feature threads company answers back into
extraction so the assignment converges conversationally. It is the highest-leverage
step toward the "AI writes the complete assignment" promise and unblocks budget/team
estimation.
