# MatchIT — Pitch Deck

> Working draft. Market figures are sourced in `docs/market-strategy.md`; every
> product claim is shipped and demonstrable.

---

## 1 · The claim

**Hiring an IT specialist takes weeks. It should take minutes.**

MatchIT is the AI staffing platform: AI understands the business problem *and*
the specialist, and does 90% of the recruiting between them.

---

## 2 · The problem

- EU IT staffing is a **€29.7B market (2025)**, growing ~5.2% a year, while
  **75% of employers cannot fill advanced roles** and the EU faces a shortage of
  up to **500,000 ICT professionals**. Demand is not the problem.
- Freelancers report platform commissions eating **20–30%** of earnings, plus
  ghosting, fake profiles and weak vetting.
- The delay is not scarcity — it is process: writing the vacancy, sourcing,
  screening calls, scheduling, paperwork. Every step is a human bottleneck.
- Existing marketplaces (HeadFirst, Malt, Upwork, LinkedIn) digitised the
  *listing*, not the *work*: they still run on search, filters, keyword CVs and
  human recruiters.

---

## 3 · The product (live today, end to end)

One loop, minutes long, every step shipped:

1. **Describe the problem in a sentence.** The concierge extracts a complete
   assignment — roles, must-have skills, budget, timeline — and asks only the
   questions a top recruiter would. Missing budgets are estimated from EU market
   rates and *flagged as estimates*.
2. **Ranked, explainable matches.** Vector recall plus a transparent score
   (skills / semantics / rate / availability / location / language) — the
   breakdown ships with every match. Multi-role assignments are filled seat by
   seat by the team builder.
3. **AI interviews.** Questions target exactly what the profile leaves unproven;
   the transcript is scored against a rubric; the hiring manager gets a
   recommendation, the specialist gets constructive feedback.
4. **Contract and money.** The engagement contract is drafted from the agreed
   terms (never invented), signed in-app, and invoiced through escrow with EU
   VAT handled correctly.

---

## 4 · Why we win

- **Evidence, not keywords.** CVs and public GitHub work are read into a skill
  graph where every skill carries a citation, and a stronger source can never be
  overwritten by a weaker one. Interviews probe the gaps. Competitors rank
  self-reported keywords.
- **Explainability as product.** Every ranking, every interview score, every
  AI estimate shows its reasoning. That is the difference between "the algorithm
  chose" and "here is why" — and it is also what EU AI regulation will demand of
  everyone else later.
- **EU-native.** GDPR export/erasure in-product, EU-pinned infrastructure by
  construction, interviews constrained to lawful questions. This is a moat in
  the exact market we start in.

---

## 5 · Business model

- **Commission** on invoiced work flowing through escrow (rate finalised at
  launch; modelled at 10–15% of net fees — half of what agencies take).
- **SaaS** for enterprises later: white-label AI staffing inside their own
  vendor pool (Epic 10).
- Unit economics are visible from day one: AI cost is metered per feature in
  the admin console, so gross margin per hire is a dashboard number, not a
  guess.

---

## 6 · Market

- **EU IT staffing: €29.7B (2025) → ~$42.7B by 2031**, 5.2% CAGR.
- Incumbents are large but slow: **HeadFirst €2.2B revenue**, **Malt €1B+
  platform volume** — both built on search, filters and human intermediation.
- Beachhead: **Dutch data & AI engineers**. The Netherlands began enforcing
  false-self-employment rules in 2025 and can levy penalties from January 2026,
  which makes *evidence of a genuine independent relationship* commercially
  urgent this year — and MatchIT generates both the contract and the evidence.
- Then adjacent skills, then Belgium and DACH. Liquidity first, reach second.

## 6b · Why now

Recruitment AI is **high-risk under the EU AI Act**: risk assessments, bias
testing, human oversight, transparency and continuous monitoring, with penalties
to **€15M or 3% of turnover**. Emotion inference in hiring is already banned.
Meanwhile *Mobley v. Workday* was certified as a collective action and HireVue
faces an ACLU discrimination complaint over AI video interviews.

Every competitor will have to retrofit explainability. MatchIT was built with it:
the score breakdown, the interview rationale, the audit log and the
human-decides rule are load-bearing architecture, not a compliance layer. The
Article 11 documentation is *generated from the prompts the product runs on*, so
it cannot drift; the transparency report is an artifact of every hire rather
than a report someone remembers to write; and there is no video interview to
defend, because we read the case law and declined to build one.

---

## 7 · Traction & state

- Full product loop live: intake → matching → interview → contract → escrow.
- 241 automated tests; 52 API endpoints; iOS app; admin analytics with funnel,
  conversion and time-to-contract in **hours** (because the promise is minutes,
  a metric in days would hide the truth), plus continuous bias monitoring.
- Every hire produces a **signed AI transparency report** — how the candidate
  was ranked, what the interview asked and why, who decided and when —
  verifiable by anyone holding it, without a MatchIT account.
- Pre-launch: waitlist open, private beta next.

---

## 8 · Ask

[To be completed with round size and use of funds. The honest framing: the
product risk is largely retired — the money buys supply-side liquidity in one
city, Stripe/APNs production wiring, and the first two hires: a founding
recruiter-in-the-loop and a growth engineer.]
