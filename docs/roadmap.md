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
- ✅ CV parsing into the skill graph (Iteration 8): every extracted skill cites
  the role or project that supports it. Also fills headline, summary,
  certifications and languages.
- ✅ GitHub repository analysis: forks and empty repos are dropped before
  prompting; skills cite the repository that evidences them.
- ✅ Skill provenance: every skill records its source (self_reported, cv,
  github, certification, interview). Merging is rank-ordered, so re-reading a CV
  never downgrades an interview-verified skill and enrichment never deletes.
- PDF→text extraction (a thin adapter in front of the CV endpoint, which already
  takes text), certification validation against issuer APIs, video-intro
  transcription.
- Identity verification flow; remaining trust score factors go evidence-based.

## Epic 4 — Matching v2
- ✅ Team builder (Iteration 7): multi-role assignments are allocated seat by
  seat rather than ranked as one list — each role is scored against its own
  skills, nobody occupies two seats, scarce roles are filled first, and a seat
  stays visibly open rather than being filled by someone who cannot do the job.
  An agent then reviews the allocation for coverage, strengths and gaps.
- Persisted assignment embeddings, LLM re-rank stage with rationale, feedback loop
  from match decisions into ranking weights.

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
- ✅ Escrow-backed invoicing (Iteration 10): the specialist bills a period, the
  company funds it into escrow, and release pays out the net fee less the
  platform commission. Money is Decimal end to end, never float.
- ✅ EU VAT: domestic supplies carry the local standard rate; intra-EU B2B is
  reverse-charged (Art. 196); outside the EU is out of scope. Commission is
  taken on the net fee, never on VAT.
- The Stripe Connect adapter itself (the provider is behind a protocol and the
  fake is complete; `StripePaymentProvider` raises until credentials exist),
  fixed-price milestones, subscriptions, dunning.

## Epic 7 — Admin portal & analytics
- ✅ Admin API (Iteration 9): funnel and conversion metrics, match/interview/trust
  quality signals, mean time from assignment to active contract, users by role,
  and AI calls attributed per feature. Admin-only, and invisible (404, not 403)
  to everyone else.
- ✅ User management: suspend/reinstate, both audited; a suspended account is
  locked out immediately on its already-issued token.
- ✅ Audit search by action and actor.
- The portal UI itself (a thin web client over these endpoints), disputes and
  fraud queues, revenue/LTV/CAC once payments land.

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

**Epic 10 — scale-out, and Epic 2's push notifications.** The product loop is
now complete end to end. What is missing is operational: Terraform/Kubernetes
manifests, matching workers behind a queue, and APNs so a specialist learns
about a match without opening the app.
