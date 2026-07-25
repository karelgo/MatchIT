# MatchIT — Data Model

System of record is PostgreSQL (SQLAlchemy 2.0, Alembic migrations). JSON columns
are JSONB on Postgres and plain JSON on SQLite (tests). All primary keys are UUIDs;
all timestamps are UTC.

```
users ──1:1── specialist_profiles
  │  └─1:1── company_profiles
  │
  └──1:N── refresh_tokens

company_profiles ──1:N── assignments ──1:N── matches ──N:1── specialist_profiles
```

## Tables (Iteration 1)

### users
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| email | citext-like (unique, lower-cased) | |
| password_hash | text, nullable | null for Apple-only accounts |
| apple_user_id | text, unique, nullable | `sub` from Apple identity token |
| full_name | text | |
| role | enum | freelancer, employee, consultancy, recruiter, hiring_manager, admin |
| is_active / is_verified | bool | |
| created_at / updated_at | timestamptz | |

### specialist_profiles
Headline, bio, skills (JSONB list of `{name, level, years}`), languages (ISO 639-1),
certifications, hourly_rate + currency, availability (hours/week, available_from),
remote_preference (remote/hybrid/onsite), country/city, travel_distance_km,
github_url/linkedin_url/website_url, years_experience, trust_score +
trust_breakdown (JSONB), embedding synced to Qdrant (`specialists` collection,
point id = profile id).

### company_profiles
Name, industry, size, country/city, website, description, verification status.

### assignments
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| company_id | FK → company_profiles | |
| raw_description | text | the natural-language problem statement(s) |
| requirements | JSONB | validated `AssignmentRequirements` from AI intake |
| status | enum | draft, open, matched, in_progress, completed, cancelled |
| created_at / updated_at | timestamptz | |

### matches
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | unique (assignment_id, specialist_id) |
| assignment_id / specialist_id | FKs | |
| score | float 0–1 | blended ranking score |
| breakdown | JSONB | per-component scores (explainability) |
| company_decision / specialist_decision | enum | pending, accepted, rejected |
| status | enum | suggested, mutual, closed — mutual when both accept |

### refresh_tokens
token_hash (SHA-256, unique), user_id FK, expires_at, revoked_at. Rotation revokes
the old row atomically with issuing the new one.

## Vector store (Qdrant)

| Collection | Point | Payload |
|---|---|---|
| `specialists` | profile embedding (cosine) | profile_id, country, remote_preference, top skills |

Assignments are embedded on demand for recall queries; persisted assignment
embeddings arrive with the re-rank stage (Epic 4).

## Roadmap tables (see docs/roadmap.md)

conversations & messages (chat), interviews (AI interview transcripts + scores),
contracts, payments/escrow ledger, reviews, notifications, audit_log.
