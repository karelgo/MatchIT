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

**Epic 5, story 1 — the AI interview agent.** Chat now carries the conversation
between a matched company and specialist, which is exactly the transport an AI
interviewer needs. Generating interview questions from the assignment plus the
candidate's skill-graph gaps, running them in-thread, and returning a scored
summary is the single biggest remaining step toward "AI does 90% of the
recruiting" — and it feeds the trust score's `interview_score` factor, which is
already wired but always zero today.
