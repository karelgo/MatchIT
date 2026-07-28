# MatchIT — AI systems

<!-- Generated from app/services/aisystems.py by scripts/generate_model_cards.py.
     Do not edit by hand: run the script. -->

MatchIT uses automated systems throughout hiring and tells you so, which is what Article 50 of the EU AI Act requires. Recruitment AI is high-risk under that Act, so each system below is documented with its purpose, its inputs, its limitations and the human oversight applied to it. No system here decides anything on its own: a person on each side accepts or rejects, and an engagement exists only once both have signed.

Each system carries a **definition fingerprint**: the first 16 hex characters of the SHA-256 of the exact prompt or parameter table it runs on. A transparency report cites the fingerprints that were in force for that hire, so a card can be matched to the decision it actually governed.

| System | Kind | Fingerprint | Output |
| --- | --- | --- | --- |
| Assignment intake analyst | llm | `52bf622856bdf53e` | AssignmentRequirements |
| Specialist ranking function | deterministic | `fc45fd8ceaec12b3` | — |
| Semantic profile and assignment embedding | embedding | `156b009a1fb92737` | — |
| Screening interview planner | llm | `96861078d4299edf` | InterviewPlan |
| Screening interview assessor | llm | `8374ab35fe1783ef` | InterviewAssessment |
| CV skill extractor | llm | `fc046e39b1602d6a` | CVExtraction |
| Public repository analyser | llm | `c6918114ce173c21` | GitHubExtraction |
| CV writer | llm | `7fd54dab243be630` | GeneratedCV |
| Team composition reviewer | llm | `428406ba43f1b698` | TeamProposal |
| Engagement contract drafter | llm | `06b1821e57db40f8` | ContractDraft |

## Assignment intake analyst

- **Key:** `intake`
- **Kind:** llm
- **Definition fingerprint:** `52bf622856bdf53e`
- **Usage-metering label:** `intake`
- **Output contract:** `AssignmentRequirements`

**Purpose.** Turn a company's free-text description of a business problem into a structured assignment: roles, seniority, must-have and nice-to-have skills, languages, location, timeline and budget.

**Inputs.**

- the company's problem statement
- the full intake dialogue, including the company's answers to clarifying questions

**What the output is used for.** the requirements the ranking function scores candidates against

**Human oversight.** The company reviews and refines the extracted assignment before any matching runs, and every field remains editable.

**Limitations and known failure modes.**

- Budget and duration are estimated from European market rates when the company states neither; estimates are flagged as such in the API and in the app, and are never presented as stated terms.
- Skill names are normalised to canonical lower-case forms, so an unusual in-house technology name may be normalised to a near neighbour.

**Personal data.**

- None about specialists. Company-side input may contain the author's own description of their team.

## Specialist ranking function

- **Key:** `ranking`
- **Kind:** deterministic
- **Definition fingerprint:** `fc45fd8ceaec12b3`
- **Usage-metering label:** not model-backed
- **Output contract:** not applicable

**Purpose.** Rank specialist profiles against a structured assignment and produce the score breakdown that is shown to both parties.

**Inputs.**

- the structured assignment
- the specialist's skills, rate, availability, location and languages
- the semantic similarity of the two texts

**What the output is used for.** the order in which a company sees candidates, and the opportunity inbox

**Human oversight.** Advisory only. The system produces no outcome by itself: a human on each side accepts or rejects, and both signatures are required before any engagement exists.

**Limitations and known failure modes.**

- Skill matching is by canonical name, so a skill the specialist has but has not recorded scores zero. The interview exists to find exactly this.
- A profile that has never been enriched from a CV or repository is scored on self-reported claims, which the score breakdown makes visible.
- No candidate is filtered out before scoring, so a low rank is a low score and not an exclusion.

**Personal data.**

- Professional attributes only: skills, years of experience, rate, availability, country, city, languages.
- Age, gender, nationality, ethnicity, health and religion are never collected, inferred or used. The CV reader is instructed to discard them even when the source document states them.

## Semantic profile and assignment embedding

- **Key:** `embedding`
- **Kind:** embedding
- **Definition fingerprint:** `156b009a1fb92737`
- **Usage-metering label:** not model-backed
- **Output contract:** not applicable

**Purpose.** Represent assignment text and profile text as vectors so that relevant experience described in different words still matches.

**Inputs.**

- the profile headline, bio, skills, certifications and languages

**What the output is used for.** the `semantic` component of the ranking function, weighted at 25%

**Human oversight.** Advisory only. The system produces no outcome by itself: a human on each side accepts or rejects, and both signatures are required before any engagement exists.

**Limitations and known failure modes.**

- Similarity reflects how the two texts are written. A terse profile scores lower on this component than a fluent one describing the same work.
- The component is capped at the weight above precisely because writing quality must not dominate evidence of skill.

**Personal data.**

- The free-text profile the specialist wrote about themselves.

## Screening interview planner

- **Key:** `interview_plan`
- **Kind:** llm
- **Definition fingerprint:** `96861078d4299edf`
- **Usage-metering label:** `interview`
- **Output contract:** `InterviewPlan`

**Purpose.** Design a short written interview aimed at the must-have skills the profile does not already evidence.

**Inputs.**

- the structured assignment
- a projection of the profile that excludes name, contact details and rate
- the must-have skills the profile does not claim

**What the output is used for.** the questions asked, each published with the rationale for asking it

**Human oversight.** Every question and its rationale are visible to both parties before and after the interview. The specialist may decline to take it.

**Limitations and known failure modes.**

- The plan is built from the profile as recorded; a profile that understates experience yields questions that feel basic.
- The prompt forbids questions about age, health, family, nationality or religion — anything that cannot lawfully inform an EU hiring decision.

**Personal data.**

- Professional profile content only. The planner is deliberately not told who the specialist is or what they cost.

## Screening interview assessor

- **Key:** `interview_assessment`
- **Kind:** llm
- **Definition fingerprint:** `8374ab35fe1783ef`
- **Usage-metering label:** `interview`
- **Output contract:** `InterviewAssessment`

**Purpose.** Score written interview answers against the assignment's requirements.

**Inputs.**

- the structured assignment
- the profile projection
- the transcript of questions and answers

**What the output is used for.** a hiring-manager recommendation, feedback for the specialist, and one input to the trust score

**Human oversight.** The recommendation is advice. The hiring manager decides, and the per-question reasoning is published so the decision can be argued with.

**Limitations and known failure modes.**

- Answers may be spoken and transcribed. Only content is scored: delivery, accent, fluency, speed and transcription artefacts are excluded by the prompt, and no audio or video is ever analysed.
- The score reflects what the transcript evidences, which is a floor on ability and never a ceiling.
- Emotion, personality and affect are not inferred. Inferring emotion in a workplace context is prohibited by the EU AI Act and MatchIT runs no such system.

**Personal data.**

- The answers the specialist chose to write or say.
- Age, gender, nationality, ethnicity, health and religion are never collected, inferred or used. The CV reader is instructed to discard them even when the source document states them.

## CV skill extractor

- **Key:** `cv_extraction`
- **Kind:** llm
- **Definition fingerprint:** `fc046e39b1602d6a`
- **Usage-metering label:** `enrichment`
- **Output contract:** `CVExtraction`

**Purpose.** Read an uploaded CV into the skill graph, with every skill citing the role or project in the document that supports it.

**Inputs.**

- the text of a CV the specialist uploaded themselves

**What the output is used for.** the specialist's own profile: skills, levels, certifications, languages

**Human oversight.** The specialist uploads their own CV, sees every extracted skill with its evidence, and can edit or remove any of it.

**Limitations and known failure modes.**

- Enrichment never deletes and never downgrades: a skill already verified by an interview outranks the same skill read from a CV.
- A scanned CV with no text layer is rejected rather than guessed at.

**Personal data.**

- Whatever the specialist's own CV contains.
- Age, gender, nationality, ethnicity, health and religion are never collected, inferred or used. The CV reader is instructed to discard them even when the source document states them.

## Public repository analyser

- **Key:** `github_extraction`
- **Kind:** llm
- **Definition fingerprint:** `c6918114ce173c21`
- **Usage-metering label:** `enrichment`
- **Output contract:** `GitHubExtraction`

**Purpose.** Infer demonstrated skills from a specialist's public repositories.

**Inputs.**

- public repository metadata for a username the specialist supplied: name, description, language, stars, size and last push

**What the output is used for.** skills on the specialist's own profile, each citing a repository

**Human oversight.** Opt-in per specialist, and the resulting skills are visible and editable.

**Limitations and known failure modes.**

- Forks and empty repositories are discarded before the model is called, so an account with only forks costs nothing and adds nothing.
- Absence of public code is never evidence against a skill.

**Personal data.**

- Public repository metadata for a username the specialist gave us.

## CV writer

- **Key:** `cv_generator`
- **Kind:** llm
- **Definition fingerprint:** `7fd54dab243be630`
- **Usage-metering label:** `cv_generator`
- **Output contract:** `GeneratedCV`

**Purpose.** Write a CV for a specialist from their evidence-backed profile.

**Inputs.**

- the specialist's own profile, including each skill's evidence

**What the output is used for.** a document the specialist may share; it feeds no ranking

**Human oversight.** Generated on request by the specialist, for the specialist.

**Limitations and known failure modes.**

- The prompt forbids inventing employers, dates, projects or outcomes, so a thin profile yields a short CV. That is the intended behaviour.

**Personal data.**

- The specialist's own profile.

## Team composition reviewer

- **Key:** `team_builder`
- **Kind:** llm
- **Definition fingerprint:** `428406ba43f1b698`
- **Usage-metering label:** `team_builder`
- **Output contract:** `TeamProposal`

**Purpose.** Explain and critique a seat-by-seat team allocation for a multi-role assignment.

**Inputs.**

- the assignment's roles and seats
- the allocation and its scores

**What the output is used for.** a written rationale, strengths and gaps shown to the company

**Human oversight.** The allocation itself is deterministic; the model explains it and does not reorder it. A seat with no viable candidate stays visibly open.

**Limitations and known failure modes.**

- Seats are filled only above a minimum score, so an open seat means no suitable candidate was found rather than none existing.

**Personal data.**

- Specialist headlines and skills for the allocated candidates.

## Engagement contract drafter

- **Key:** `contract`
- **Kind:** llm
- **Definition fingerprint:** `06b1821e57db40f8`
- **Usage-metering label:** `contract`
- **Output contract:** `ContractDraft`

**Purpose.** Draft an EU engagement contract from the assignment and the commercial terms both parties agreed.

**Inputs.**

- the structured assignment
- the agreed terms
- both parties' countries

**What the output is used for.** a draft both parties read and sign in-app

**Human oversight.** Both parties read the draft and sign it; nothing takes effect without both signatures. The draft is not legal advice.

**Limitations and known failure modes.**

- The model never invents a rate, date, duration or notice period: anything missing goes to `open_points` for a lawyer instead of being guessed.

**Personal data.**

- The parties' names, countries and agreed commercial terms.
