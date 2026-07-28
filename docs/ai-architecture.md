# MatchIT — AI Architecture

AI is the product. Every AI capability is built on the same three primitives, all
provider-agnostic and all testable offline:

| Primitive | Protocol | Production impls | Test impl |
|---|---|---|---|
| Structured reasoning | `app.ai.llm.ChatModel` | Anthropic, OpenAI (Azure OpenAI & Gemini via the same interface) | `FakeChatModel` |
| Semantic representation | `app.ai.embeddings.EmbeddingModel` | OpenAI `text-embedding-3-small` | `FakeEmbeddingModel` (deterministic hashing) |
| Semantic retrieval | `app.services.vector.VectorIndex` | Qdrant | `InMemoryVectorIndex` |

`ChatModel.complete_structured(...)` always returns a **validated Pydantic model**:
Anthropic via forced tool-use, OpenAI via `json_schema` response format. Prompts live
in `app/ai/prompts.py`; models never see raw database rows — profiles and
assignments are projected to minimal, GDPR-clean views before prompting.

## Capability map

### 1. Assignment intake (AI Concierge) — shipped in Iteration 1

`IntakeService.extract()` turns a natural-language problem statement —
*“We need two Microsoft Fabric architects to migrate our data warehouse within six
months”* — into `AssignmentRequirements`:

- roles (title, count, seniority), must-have vs nice-to-have skills
- languages, location & remote policy, start date / duration
- hourly budget range + currency, certifications, industry, a clean summary
- `clarifying_questions`: what the AI still needs to ask — this is what makes the
  concierge conversational rather than a form

The extraction is schema-constrained, validated, and stored on the assignment as
JSONB. The intake is **multi-turn**: the dialogue is persisted on the assignment
(`intake_history`), and `POST /assignments/{id}/refine` feeds each company answer
back through extraction over the full "Company:/Concierge:" transcript, so later
answers refine or override earlier statements and answered questions are never
re-asked. When budget or duration are stated nowhere in the conversation, the
model estimates them from current EU market rates and flags them
(`budget_is_estimated` / `duration_is_estimated`) — stated values are never
flagged.

### 2. Matching engine — shipped in Iteration 1

Matching is a transparent hybrid, not a black box. For each (assignment, specialist)
pair the engine computes a weighted blend, each component in `[0, 1]`:

| Component | Weight | Signal |
|---|---|---|
| `skills` | 0.40 | must-have coverage (nice-to-haves at ⅓ weight) |
| `semantic` | 0.25 | cosine similarity of assignment ↔ profile embeddings |
| `rate` | 0.10 | specialist rate inside/near budget band |
| `availability` | 0.10 | can start by the requested date, weekly hours fit |
| `location` | 0.10 | remote policy compatibility / on-site distance |
| `language` | 0.05 | required languages spoken |

The full breakdown is persisted on every match — companies see *why* someone was
ranked #1, which is a trust feature and a GDPR-explainability requirement.
Candidate recall is vector-first (Qdrant top-K) with the deterministic blend as the
ranking stage; an LLM re-rank stage slots in after ranking (Epic 4).

### 3. Skill graph

Specialist skills are stored as `{skill, level 0-10, evidence}` triples. Iteration 1
populates them from profile input; the roadmap adds automatic enrichment from CV
parsing, GitHub analysis, certification validation and interview outcomes — the
graph *converges on evidence*, replacing self-reported keywords.

### 4. Trust score — shipped in Iteration 1

`TrustScoreService` computes a 0–100 score from verification, reviews, completed
projects, response time, interview scores and payment history, with explicit
weights and a persisted factor breakdown. Deterministic and unit-tested; AI-derived
factors (interview scoring, fraud signals) plug in as additional factors.

### 5. AI interview agent — shipped in Iteration 4

Two schema-constrained calls, both provider-agnostic:

1. **Plan** (`InterviewService.plan`) — given the assignment and the specialist's
   profile, produce 3–6 questions. The prompt receives an explicit
   `unproven_must_have_skills` list (must-haves the profile does not claim at all),
   and the agent is instructed to spend the interview on those rather than on what
   the profile already evidences. Each question carries a `rationale` the hiring
   manager reads, so question selection is explainable like ranking is.
2. **Assess** (`InterviewService.assess`) — given the transcript, return
   `overall_score`, per-question scores with reasoning, strengths, development
   areas, concerns and a hire recommendation.

Two deliberate constraints:

- **The interviewer never learns who it is interviewing.** `profile_view()` projects
  the profile down to headline, bio, skills, experience, certifications and
  languages — no identifiers, no location, no rate. A screening agent has no
  business knowing the candidate's name or price, and a unit test asserts those
  fields cannot reach the prompt.
- **EU hiring law is in the prompt, not the review queue.** The planner is
  instructed never to ask about age, health, family, nationality or religion.

On completion the score flows into `TrustScoreService` as the `interview_score`
factor — the first factor the platform can actually evidence. The remaining factors
stay zero until the epics that produce them ship, so the score never overstates
what is known.

### 6. Further AI agents (Epics 4–6)

Specialised agents are thin orchestrations over the same primitives, each with its
own prompt, output schema and tool access: Recruiter, Contract Generator, Project
Estimator, Team Builder, Career Coach, Salary Advisor, Skills Validator, Fraud
Detection.

Spoken answers reach the shipped interview agent as text: audio is transcribed and
discarded inside the request, and the transcript is what is stored and scored. There
is no video path and there will not be one — see `docs/market-strategy.md` §2.2.
Nothing in MatchIT infers emotion, affect or personality, which the EU AI Act
prohibits outright in a workplace context.

### 7. Documenting the systems

`app/services/aisystems.py` is the registry of every automated system, including the
deterministic ranking function — it decides who a company ever sees, so documenting
only the language models would document the easy half. Each entry points at the
actual prompt constant or parameter table the feature runs on and carries a SHA-256
fingerprint of it, so editing a prompt changes the published card in the same commit.
`scripts/generate_model_cards.py` writes `docs/ai-systems.md` from the registry and a
test fails if the committed document has drifted.

Per-hire, `app/services/transparency.py` assembles the signed transparency report:
the weighted ranking breakdown, the interview questions with the rationale for each,
the per-answer scores, who decided and when, and the fingerprints in force at the
time. Both parties receive the identical document, and anyone holding it can verify
it at `POST /api/v1/transparency-reports/verify` without an account.

## Cost & observability

- Every model call is tagged (feature, model, tokens) for per-feature unit
  economics; budget alerts per provider.
- Providers are configured per capability: cheap/fast models for extraction,
  frontier models for interviews and contracts.
- All prompts are versioned in code; output schemas make regressions testable.
