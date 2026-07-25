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
JSONB. Follow-up answers re-run extraction over the accumulated conversation.

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

### 5. AI agents (Epics 4–6)

Specialised agents are thin orchestrations over the same primitives, each with its
own prompt, output schema and tool access: Recruiter, Interviewer, Contract
Generator, Project Estimator, Team Builder, Career Coach, Salary Advisor, Skills
Validator, Fraud Detection. The interview agent additionally consumes video
transcripts (see roadmap).

## Cost & observability

- Every model call is tagged (feature, model, tokens) for per-feature unit
  economics; budget alerts per provider.
- Providers are configured per capability: cheap/fast models for extraction,
  frontier models for interviews and contracts.
- All prompts are versioned in code; output schemas make regressions testable.
