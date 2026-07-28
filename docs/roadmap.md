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
- ✅ Push notifications (Iteration 11): device registration, and delivery on
  mutual match, new message and contract signature. Delivery is best-effort by
  construction — a failed push never fails the action that triggered it.
- Team composition proposals from the concierge (the team builder exists; the
  concierge does not yet offer it conversationally).
- AI assistant in thread, code snippets & diagram attachments.

## Epic 3 — Supply-side intelligence
- ✅ CV parsing into the skill graph (Iteration 8): every extracted skill cites
  the role or project that supports it. Also fills headline, summary,
  certifications and languages.
- ✅ GitHub repository analysis: forks and empty repos are dropped before
  prompting; skills cite the repository that evidences them.
- ✅ Skill provenance: every skill records its source (self_reported, cv,
  github, certification, interview). Merging is rank-ordered, so re-reading a CV
  never downgrades an interview-verified skill and enrichment never deletes.
- ✅ PDF CV upload (Iteration 12): text extraction with distinct, actionable
  errors for the three real failure modes — not a PDF, password-protected, and
  the common one, a scanned CV with no text layer. No model call is paid for an
  unreadable file. iOS gains an Import section (PDF picker + GitHub username).
- Certification validation against issuer APIs.
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
- ⛔ **In-app video interviews — dropped deliberately.** See
  `docs/market-strategy.md` §2.2: AI video interviewing is the subject of the
  ACLU's complaint against HireVue (deaf and non-white applicants) and of
  *Baker v. CVS*, and it edges toward the EU AI Act's outright prohibition on
  inferring emotions in hiring. MatchIT's text-based, asynchronous interview is
  more accessible and more defensible, and is a positioning asset rather than a
  gap.
- ✅ **Async voice answers (Iteration 15)** — the replacement, now shipped.
  Speak an answer instead of typing it: iOS dictates on-device and posts text,
  and `POST /matches/{id}/interview/answer/audio` transcribes server-side for
  clients that cannot. Audio is discarded inside the request; the transcript is
  what is stored, scored and reported. The assessor prompt now forbids scoring
  delivery, disfluency or transcription artefacts, so the medium cannot move a
  score. No audio or video is ever analysed.
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
- ✅ Bias monitoring (Iteration 15): selection rate, adverse-impact ratio and
  mean scores per cohort across four observable dimensions — banded experience
  (the age proxy), country, working language and remote preference — with the
  four-fifths rule flagged and cohorts under five decisions shown but never
  judged. The page states what it cannot measure: MatchIT collects no protected
  attributes, so these are proxies and a flag is a prompt to investigate rather
  than a finding. `GET /admin/bias`, with a portal tab verified in real Chromium.
- ✅ Portal UI (Iteration 14): a single-file vanilla-JS client served by the
  API itself at `/admin-portal` — same origin, so no CORS surface to widen, and
  it ships inside the same image. Login, funnel and AI-usage dashboards, user
  suspension, audit search. All data reaches the DOM via `textContent`, never
  `innerHTML`: the audit log contains attacker-supplied strings (the email
  typed into a failed login). Verified end to end with real Chromium.
- Disputes and fraud queues, revenue/LTV/CAC once payments carry real money.

## Epic 8 — Trust & safety, compliance
- ✅ Rate limiting (Iteration 6): fixed-window, Redis-backed so the budget is
  shared across replicas, on registration and login.
- ✅ Append-only audit log: registration, login success/failure, exports and
  erasures. The actor FK is SET NULL on delete, never CASCADE — erasing an
  account must not erase the evidence of what it did.
- ✅ GDPR data-subject tooling: Article 15/20 export and Article 17 erasure,
  refused while a contract is active (Art. 17(3)).
- ✅ AI transparency report (Iteration 15): one signed artifact per hiring
  decision — the weighted ranking breakdown, the interview questions with the
  rationale for each, the per-answer scores, who decided and when, and the AI
  systems involved at the exact prompt fingerprint in force. Both parties get
  the identical document, including the AI's recommendation: the live interview
  API projects per viewer so a candidate is not reading "no" mid-screening, but
  a decision record that concealed the conclusion would not be a transparency
  report. Issued only once the company has decided. Signed with an HMAC under a
  key derived from the application secret, and verifiable at
  `POST /transparency-reports/verify` **without an account** — an auditor
  holding the document should not have to sign up here.
- ✅ AI system registry and model cards (Iteration 15): Article 11 technical
  documentation generated from the prompt constants and parameter tables the
  features actually run on, each fingerprinted, so a prompt edit changes the
  published card in the same commit. The deterministic ranking function is
  documented alongside the language models — it decides who is ever seen.
  `GET /ai/systems`, `docs/ai-systems.md`, and a test that fails on drift.
- ✅ Engagement evidence pack (Iteration 15): contract, scope, clause coverage,
  invoices, signature trail and Wet DBA independence indicators as one document,
  each indicator saying what was observed and which way it points. It refuses to
  draw a conclusion — misclassification is judged on the whole relationship, and
  a checklist that implied otherwise would be worth less than nothing to whoever
  relied on it. Signing a contract now writes the audit entry the action enum
  had always declared.
- ✅ Specialist feedback (Iteration 15): every closed opportunity carries the
  reason — which components cost the most, which must-have skills were missing
  by name, and what would change it. Derived from the persisted breakdown, so it
  costs nothing, is always available, and cannot invent a reason that was not
  the real one. `GET /matches/{id}/feedback`, with `GET /matches/history` and a
  Past opportunities screen in the app.
- SOC2 controls, anomaly detection, admin-facing audit search.

## Epic 9 — Delight
- ✅ Home-screen widget (Iteration 13): opportunity count and top match, small
  and medium families. Widgets don't authenticate — the app writes a snapshot
  to the App Group store and reloads timelines, so the widget never touches the
  network.
- ✅ Interview Live Activity: lock-screen and Dynamic Island progress while a
  screening interview is in flight, specialist-side only, ended on completion.
  Best-effort by construction — a missing island never affects the interview.
- ✅ Voice-first concierge: live dictation streams into the problem description
  (SFSpeechRecognizer), appending to whatever was typed.
- ✅ AI-generated CV: written from the evidence-backed skill graph only — the
  prompt forbids inventing employers, dates or outcomes, and a thin profile
  yields a short CV by design. The model returns structure; the document is
  rendered deterministically server-side. Shareable from the profile.
- ✅ App Intents: "Show my MatchIT opportunities/messages" for Siri, Shortcuts
  and Spotlight.
- Apple Intelligence integration beyond App Intents.

## Epic 10 — Scale-out
- ✅ Kubernetes manifests (Iteration 11): API deployment with an HPA, migrations
  as a pre-upgrade Job rather than an init container (three replicas would race
  three migrations), and a liveness probe that touches no dependency so a slow
  database cannot cause a cluster-wide restart loop.
- ✅ Terraform for the stateful tier: encrypted Postgres and Redis, both private,
  with the region validated to be EU-only — MatchIT holds EU personal data, so a
  `us-east-1` typo would be a transfer, not a deployment detail.
- Matching workers behind a queue, chat gateway extraction, enterprise
  white-label.

## Market strategy

`docs/market-strategy.md` holds the sourced competitive research and the
differentiation plan. Its three load-bearing conclusions:

1. **Compliance is the product.** EU AI Act explainability obligations are
   architectural, and MatchIT already satisfies them. Highest-value next build:
   an **AI Transparency Report** per hire, followed by bias monitoring in admin
   analytics and a **DBA evidence pack** export.
2. **Candidate dignity is the growth loop**, not a nicety — the market is
   turning against black-box hiring AI, and MatchIT is already on the right side.
3. **Liquidity before reach.** One vertical (Dutch data/AI engineers), supply
   seeded first, north star = *assignment fill rate within 72 hours*.

## Next up (recommended)

**Everything left needs the outside world.** `StripePaymentProvider`,
`APNsSender` and `OpenAITranscriber` need real credentials; the iOS project
needs one macOS verification pass (three targets: app, free-provisioning app,
widget extension) to make its CI job a merge gate; the legal drafts need
counsel. Every purely-code item in the original brief, and every item on the
market-research build list, has shipped.

Two things worth doing when there is real traffic: publish the transparency
report signing key so third parties can verify without calling MatchIT at all,
and revisit the bias dimensions once cohorts are large enough for the
four-fifths rule to mean something.
