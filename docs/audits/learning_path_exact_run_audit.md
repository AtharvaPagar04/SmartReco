# SmartReco Exact Learning Path Generation Audit

Audit date: 2026-08-08  
Repository: `/home/arch/DEV/SmartReco`  
Audit mode: read-only; no application, database, Qdrant, or configuration changes

## Executive summary

The exact screenshot questionnaire is parsed correctly, but the current path builder does not preserve frontend specificity beyond a broad catalog category. `FRONTEND`, `BACKEND`, `FULLSTACK`, `MOBILE`, and `API` all map to `Web Development`; `_score()` then gives every `Web Development` course a `+25` primary-domain category bonus. This is the first verified selection-causing source of domain drift.

The current deterministic selector also discards semantic ordering. It sorts candidates only by `_score()`, then difficulty/title/id tie-breakers. It does not use `RecommendationCandidate.semantic_score`, does not enforce domain composition, and does not enforce monotonic difficulty. A controlled in-memory run using exactly the eight courses shown in the reported path reproduces the reported order exactly:

1. FastAPI Backend Development — `54.8421`
2. Building Real-Time Web Apps with WebSockets — `45.4737`
3. Web Performance Optimization Masterclass — `45.1053`
4. Next.js Fullstack Architecture — `43.1053`
5. Accessible Interface Craft — `34.2105`
6. Design Systems That Scale — `29.2105`
7. Design Systems for Enterprise Apps — `24.4737`
8. Introduction to Agentic AI — `23.7368`

This proves the deterministic reranker can explain the sequence if those eight courses reached the selector. It does **not** prove their Qdrant ranks: the exact Mesh embedding call timed out in this environment before producing a query vector, and the current local Qdrant store was concurrently locked. No synthetic vector or stale backup was substituted.

FastAPI is therefore explained with high confidence at the reranking stage: it receives the broad frontend category bonus, matches `apis`, `build`, `development`, `python`, and `web`, receives the production and profile terms, and has no domain-specific rejection. Agentic AI has no frontend/UI/UX category or tag contribution, but its score is still `23.7368`, above the selector's `18` tail threshold. If it is present in the candidate set, it is eligible; whether it entered through Qdrant or a fallback in the reported run is unverified.

The exact eight-course path is not present in the current database. The nearest persisted path has the same Frontend/Extended/23-hour/5-week shape but a different eight-course sequence, `USD 446.00`, and `used_mesh=false`. The screenshot's `USD 360.00` path is consequently not a persisted row that can be conclusively reconstructed from this checkout.

### Final diagnosis

- Primary root cause: taxonomy collision plus broad `+25` primary category scoring. **HIGH confidence.**
- Secondary root cause: deterministic reranking replaces semantic order and has no final domain validator. **HIGH confidence.**
- Contributing factors: the exact UI path submits `EXTENDED` with hidden `requested_course_count=4`; the selector still targets eight from `path_length`; prior-skill tokens alter lexical-score normalization; a long path exposes lower-scoring tail candidates. **HIGH/MEDIUM confidence, depending on item.**
- First verified selection-causing drift: `_profile_for_input()` projects `FRONTEND` to `Web Development`, then `_score()` treats all Web Development courses as primary-domain matches. **HIGH confidence.**
- Exact semantic provenance of FastAPI and Agentic AI: **UNVERIFIED** because the bounded embedding/Qdrant test could not complete.

## Audit scope and methodology

### Scope

Inspected the live browser form, router, Pydantic schema, learning-path service, retrieval service, vector store, Mesh services, models, templates, tests, current SQLite rows, and local Qdrant storage metadata. Executed only read-only SQL, bounded read-only vector/embedding attempts, pure in-memory scoring/selection, and existing tests.

No endpoint for path generation, draft saving, replacement, feedback, migration, seed, vector write, or profile refresh was called.

### Evidence labels

- **FACT** — directly observed in source or read-only state.
- **TEST RESULT** — produced by a pure in-memory diagnostic.
- **INFERENCE** — follows from observed code and measured values.
- **UNVERIFIED** — the required live observation could not complete.
- **HYPOTHESIS** — plausible but not established by this audit.

## Exact learner input

The UI uses checkbox/radio values, not the displayed labels, and the form's `EXTENDED` value is the displayed “Deep path — 8 courses” option.

| Displayed value | HTML field | Raw submitted value | Pydantic field | Internal code | Persisted value / note |
|---|---|---|---|---|---|
| Frontend Development | `selected_domains` | `FRONTEND` | `primary_domain` | `FRONTEND` | `FRONTEND` |
| UI/UX Design | `selected_domains` | `UX` | `secondary_domains` | `UX` | `["UX"]` |
| Build a production application | `goals` | `PRODUCTION` | `goals` | `PRODUCTION` | first goal; also exposed as `.goal` |
| Understand advanced concepts | `goals` | `ADVANCED` | `goals` | `ADVANCED` | second goal, but current path profile/scoring reads only `.goal` |
| Some familiarity | `level` | `FAMILIAR` | `level` | `FAMILIAR` | `FAMILIAR` |
| Production-focused examples | `learning_preferences` | `PRODUCTION` | `learning_preferences` | `PRODUCTION` | `["PRODUCTION"]` |
| Python | `prior_skills` | `PYTHON` | `prior_skills` | `PYTHON` | included in input and score tokens |
| Git | `prior_skills` | `GIT` | `prior_skills` | `GIT` | included in input and score tokens |
| APIs | `prior_skills` | `APIS` | `prior_skills` | `APIS` | included in input and score tokens |
| Prompt Engineering | `prior_skills` | `PROMPT_ENGINEERING` | `prior_skills` | `PROMPT_ENGINEERING` | included in input and score tokens |
| Practice exercises | `format_preferences` | `PRACTICE` | `format_preferences` | `PRACTICE` | included in input and score tokens |
| Projects | `format_preferences` | `PROJECTS` | `format_preferences` | `PROJECTS` | format only; no project bonus because learning preference `PROJECTS` was not selected |
| 5 hours/week | `weekly_hours` | `5` | `weekly_hours` | integer `5` | `5` |
| Deep path — 8 courses | `path_length` | `EXTENDED` | `path_length` | `EXTENDED` | `EXTENDED`; `_path_bounds()` returns `(8, 8)` |
| Hidden requested count | `requested_course_count` | `4` by template default | `requested_course_count` | integer `4` | persisted as `4`; ignored for bounds when `path_length=EXTENDED` |
| None | `optional_instruction` | empty string | `optional_instruction` | `""` | persisted as empty string in `input_json` |

The exact in-memory object used for diagnostics was:

```json
{
  "primary_domain": "FRONTEND",
  "secondary_domains": ["UX"],
  "goals": ["PRODUCTION", "ADVANCED"],
  "level": "FAMILIAR",
  "learning_preferences": ["PRODUCTION"],
  "prior_skills": ["PYTHON", "GIT", "APIS", "PROMPT_ENGINEERING"],
  "format_preferences": ["PRACTICE", "PROJECTS"],
  "weekly_hours": 5,
  "target_weeks": null,
  "budget_type": "FLEXIBLE",
  "budget_scope": "PATH",
  "budget_amount": null,
  "currency": "USD",
  "path_length": "EXTENDED",
  "requested_course_count": 8,
  "optional_instruction": "",
  "quick_instructions": []
}
```

The object used `requested_course_count=8` for the explicit ablation because the audit prompt specifies the actual requested count. The browser template currently defaults its hidden field to `4`; `EXTENDED` still forces an eight-course bound in `_path_bounds()`. This is a UI/persistence observability mismatch, not the cause of FastAPI's score.

## Pipeline architecture and evidence

### Browser to persisted input

**FACT — `app/templates/path_builder/index.html` and `app/static/js/path-builder.js`:** selected domains are submitted as `selected_domains`; the first selected domain is primary and the next values are secondary. The deep UI option submits `EXTENDED`. `requested_course_count` is hidden and defaults to `4`.

**FACT — `app/routers/learning_paths.py:_raw_form()` and `_parse_input()`:** `_raw_form()` orders domains, converts list fields, carries the raw string values, and passes the result to `LearningPathInput.model_validate()`.

**FACT — `app/schemas/learning_path.py:LearningPathInput`:** validators reject unsupported domain, goal, level, preference, skill, and format codes. Legacy singular `goal`/`format_preference` values are normalized into lists.

**FACT — `app/services/learning_path_service.py:create_learning_path()`:** the path stores `path_input.model_dump(mode="json")` in `LearningPath.input_json`, stores the first goal in `goal_code`, and creates `LearningPathItem` rows after selection.

### Retrieval and selection

```text
_raw_form()
  -> LearningPathInput
  -> build_or_refresh_profile() [production path; writes profile state]
  -> _profile_for_input()
  -> build_retrieval_query()
  -> retrieve_candidates() [embedding + Qdrant, or SQL fallback]
  -> retrieve_sql_fallback() fills candidate pool if needed
  -> _select_courses() [deterministic score sort]
  -> create LearningPath and LearningPathItem rows
```

The audit did not call `build_or_refresh_profile()` because it writes. Stored profile JSON was read directly for a bounded behavior comparison.

## Actual stored path

### Exact-match result

**FACT:** no current `learning_paths` row matches all of the following simultaneously: `FRONTEND`, secondary `UX`, goals `PRODUCTION/ADVANCED`, level `FAMILIAR`, one `PRODUCTION` learning preference, four listed prior skills, `PRACTICE/PROJECTS` formats, 5 hours, `EXTENDED`, eight items, and the reported course sequence.

The screenshot sequence and totals were therefore not treated as a persisted fact.

### Nearest persisted row

The nearest row by Frontend + Extended + eight items + 23 hours + 5 weeks was:

| Field | Observed value |
|---|---|
| Path ID | `65e07409-0b17-4c5e-af26-af3af6444f69` |
| Status | `READY` |
| Created | `2026-08-05 22:04:11` |
| Title | `Your Frontend Development learning path` |
| Primary domain | `FRONTEND` |
| Secondary domains | `PRODUCT`, `UX` |
| Goals | `CURRENT_ROLE`, `PRODUCTION` |
| Level | `FOUNDATIONS` |
| Learning preferences | `PROJECTS`, `PRODUCTION` |
| Path mode | `EXTENDED` |
| Stored requested count | `4` |
| Actual item count | `8` |
| Total hours | `23` |
| Estimated weeks | `5` |
| Total price | `USD 446.00` |
| Used semantic retrieval | `NO` (`used_mesh=0`) |
| Used SQL fallback | `YES` (`used_fallback=1`) |
| Generation run | `SUCCEEDED`, `16 -> 8` candidates/items |

Its items were:

| Stage | Course | Category | Difficulty | Price | Hours |
|---:|---|---|---|---:|---:|
| 1 | Web Performance Optimization Masterclass | Web Development | ADVANCED | 59 | 3 |
| 2 | Building Real-Time Web Apps with WebSockets | Web Development | INTERMEDIATE | 49 | 3 |
| 3 | Next.js Fullstack Architecture | Web Development | INTERMEDIATE | 79 | 4 |
| 4 | Design Systems for Enterprise Apps | UI/UX Design | INTERMEDIATE | 65 | 3 |
| 5 | AI Product Roadmap Strategy | Product Management | INTERMEDIATE | 49 | 3 |
| 6 | Product Discovery Fieldwork | Product Management | BEGINNER | 35 | 2 |
| 7 | Polars for High-Performance Data Processing | Data Science | INTERMEDIATE | 45 | 3 |
| 8 | Small Language Models in Edge Production | Artificial Intelligence | INTERMEDIATE | 65 | 4 |

**Interpretation:** this row confirms that the current database contains the same broad failure shape—an eight-course Frontend path with unrelated tail material—but it is not the screenshot run. The screenshot total of `USD 360.00` and its FastAPI/Agentic sequence are not persisted here.

## Profile generation and exact retrieval query

### Exact path-only profile

**FACT — `app/services/learning_path_service.py:_profile_for_input()`:** the exact input produces:

```json
{
  "top_categories": [
    {"name": "Web Development"},
    {"name": "UI/UX Design"}
  ],
  "top_tags": [
    {"name": "frontend"},
    {"name": "ui"},
    {"name": "design"},
    {"name": "ux"}
  ],
  "top_search_terms": [
    {"term": "Build a production application"},
    {"term": "Practice exercises"},
    {"term": "Projects"},
    {"term": "Production-focused examples"},
    {"term": "Python"},
    {"term": "Git"},
    {"term": "APIs"},
    {"term": "Prompt Engineering"}
  ],
  "confidence": 1.0
}
```

The exact query passed to `build_retrieval_query()` is:

```text
Interested in Web Development, UI/UX Design, frontend, ui, design, ux, and searches for Build a production application, Practice exercises, Projects, Production-focused examples.
```

**FACT:** prior skills are added to `top_search_terms`, but the query builder takes only the first four terms. Therefore Python, Git, APIs, and Prompt Engineering do not reach the exact baseline retrieval query unless earlier terms are removed or reordered. They do reach `_score()` through the explicit token set.

**FACT:** the second goal `ADVANCED` is not present in the query. `LearningPathInput.goal` returns only `goals[0]`, and `_profile_for_input()` uses `GOALS[path_input.goal]`.

### Stored behavior profile comparison

The exact screenshot user cannot be identified from the absent path row without exposing or assuming an identity. For a bounded diagnostic, the stored profile associated with the nearest persisted Frontend/Extended path was merged in memory. Its non-sensitive leading aggregates included `UI/UX Design`, `Agentic AI`, `Python`, `Data Science`, and `Artificial Intelligence` categories, plus `evaluation`, `python`, `accessibility`, `agents`, and `ai workflows` tags.

The merged query remained dominated by the exact input's first four terms because `_profile_for_input()` prepends exact terms and `build_retrieval_query()` truncates to four. **FACT:** behavior changes the retrieval profile/candidate pool, but `create_learning_path()` calls `_select_courses(candidates, path_input, _profile_for_input(path_input, {}))`; the stored behavior profile is not used as a direct deterministic ranking profile.

## Qdrant and Mesh audit

### Code semantics

| Question | Result | Evidence |
|---|---|---|
| Chat LLM used for course selection? | NO | `create_learning_path()` calls retrieval and `_select_courses()`; no `mesh_chat_service.generate_json()` call |
| Chat LLM used for sequencing? | NO | sequencing is `enumerate(courses)` after `_select_courses()` |
| Chat LLM used for explanation text? | NO | `_reason()` and `_next_text()` are local f-strings |
| Embedding model used? | YES when semantic retrieval succeeds | `recommendation_retrieval_service.retrieve_candidates()` calls `embed_text()` |
| Qdrant semantic retrieval used? | YES when configured and reachable | `retrieve_candidates()` calls `VectorStore.search_courses()` |
| SQL fallback used? | YES on low confidence, missing Mesh key, semantic error, or candidate shortage | `_sql_candidates()` and `candidate_courses()` |
| Meaning of `used_mesh` | Semantic retrieval path, not chat | `candidate_courses()` returns `used_semantic and not used_sql_fallback`; `create_learning_path()` stores that as `used_mesh` |

`learning_path_chat_model` exists in settings but is not used by the learning-path service. The recommendation graph has separate Mesh chat code; that is not the learning-path course-selection path.

### Bounded live test

Current settings reported:

- Mesh embedding model: `openai/text-embedding-3-small`
- Qdrant mode: local
- Qdrant collection: `smartreco_courses`
- Candidate limit: `16`
- Maximum selected courses: `8`
- Current SQLite Qdrant point rows: `60`

**TEST RESULT:** a bounded exact embedding/retrieval attempt timed out after 12 seconds before returning a vector. A read-only scroll against the current local Qdrant store also timed out; a second client reported the current storage folder as already accessed. The backup snapshot was readable and reported 72 points, but it was not used for exact retrieval because it is not current state and the exact query vector was unavailable.

Therefore:

| Required semantic evidence | Status |
|---|---|
| Exact query string | VERIFIED |
| Production candidate limit | VERIFIED: 16 |
| Exact Qdrant candidate list | UNVERIFIED |
| Exact Qdrant semantic scores | UNVERIFIED |
| FastAPI Qdrant rank | UNVERIFIED |
| Agentic AI Qdrant rank | UNVERIFIED |
| Qdrant-to-final rank movement | UNVERIFIED |

No semantic rank was fabricated from the screenshot order, a synthetic vector, or the backup store.

## Deterministic score formula

**FACT — `app/services/learning_path_service.py:_score()`:**

```text
score = 45 * |explicit_tokens ∩ course_text_tokens| / max(1, |explicit_tokens|)

for each domain, primary first:
  category bonus = 25 (primary) or 8 (secondary) if course.category is in domain.categories
  tag bonus = 8 (primary) or 3 (secondary) per exact lower-case tag overlap

level bonus = max(0, 12 - 5 * abs(course_difficulty - learner_level))
project bonus = 8 if learning_preferences contains PROJECTS and final_project exists
production bonus = 7 if learning_preferences contains PRODUCTION and text contains
                   production/reliability/deployment/operations
profile bonus = 4 if course.category equals profile.top_categories[0].name
```

For the exact input, the explicit token count is `19`. `PROJECTS` is a format preference, not a learning preference, so the project bonus is `0` for every course.

### Controlled reported-eight candidate set

This is a pure in-memory test using the eight titles in the report. It is **not** a Qdrant result table.

| Deterministic rank / final stage | Course | Category | Semantic score | Deterministic score | Classification by current catalog category |
|---:|---|---|---:|---:|---|
| 1 / 1 | FastAPI Backend Development | Web Development | unavailable | 54.8421 | primary by broad category; backend-specific by title/tags |
| 2 / 2 | Building Real-Time Web Apps with WebSockets | Web Development | unavailable | 45.4737 | primary by broad category; cross-domain in content |
| 3 / 3 | Web Performance Optimization Masterclass | Web Development | unavailable | 45.1053 | primary |
| 4 / 4 | Next.js Fullstack Architecture | Web Development | unavailable | 43.1053 | primary by broad category; full-stack-specific by title/tags |
| 5 / 5 | Accessible Interface Craft | UI/UX Design | unavailable | 34.2105 | secondary |
| 6 / 6 | Design Systems That Scale | UI/UX Design | unavailable | 29.2105 | secondary |
| 7 / 7 | Design Systems for Enterprise Apps | UI/UX Design | unavailable | 24.4737 | secondary |
| 8 / 8 | Introduction to Agentic AI | Agentic AI | unavailable | 23.7368 | out-of-domain |

The current selector reproduces exactly this order from this candidate set. It sorts by deterministic score, not by semantic score, and its `18` threshold is checked only after the first course has been chosen.

### Component breakdown

| Course | Matched explicit tokens | Token | Primary category | Secondary category | Primary tags | Secondary tags | Level | Project | Production | Profile | Total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FastAPI Backend Development | `apis`, `build`, `development`, `python`, `web` | 11.8421 | 25 | 0 | 0 | 0 | 7 | 0 | 7 | 4 | 54.8421 |
| Building Real-Time Web Apps with WebSockets | `build`, `development`, `python`, `web` | 9.4737 | 25 | 0 | 0 | 0 | 7 | 0 | 0 | 4 | 45.4737 |
| Web Performance Optimization Masterclass | `development`, `production`, `web` | 7.1053 | 25 | 0 | 0 | 0 | 2 | 0 | 7 | 4 | 45.1053 |
| Next.js Fullstack Architecture | `build`, `development`, `web` | 7.1053 | 25 | 0 | 0 | 0 | 7 | 0 | 0 | 4 | 43.1053 |
| Accessible Interface Craft | `build`, `design`, `engineering`, `practice`, `ui`, `ux` | 14.2105 | 0 | 8 | 0 | 0 | 12 | 0 | 0 | 0 | 34.2105 |
| Design Systems That Scale | `build`, `design`, `engineering`, `practice`, `ui`, `ux` | 14.2105 | 0 | 8 | 0 | 0 | 7 | 0 | 0 | 0 | 29.2105 |
| Design Systems for Enterprise Apps | `design`, `engineering`, `ui`, `ux` | 9.4737 | 0 | 8 | 0 | 0 | 7 | 0 | 0 | 0 | 24.4737 |
| Introduction to Agentic AI | `build`, `prompt` | 4.7368 | 0 | 0 | 0 | 0 | 12 | 0 | 7 | 0 | 23.7368 |

### FastAPI provenance

- **FACT:** FastAPI's catalog category is `Web Development`; its tags are `fastapi`, `apis`, `python`, and `async`.
- **FACT:** `FRONTEND.categories` contains `Web Development`, so `_score()` adds the full primary category bonus of `25`.
- **FACT:** the exact score matched `apis`, `build`, `development`, `python`, and `web`; the prior-skill-related overlap is lexical token overlap, not a separate Python/APIs feature.
- **FACT:** the production text rule adds `7`; the path-only profile adds `4` because its first category is `Web Development`.
- **TEST RESULT:** FastAPI is rank 1 in the reported-eight candidate set and becomes Stage 1.
- **UNVERIFIED:** its Qdrant semantic rank and semantic score.

### Agentic AI provenance

- **FACT:** `Introduction to Agentic AI` is active, category `Agentic AI`, tags `agents`, `foundations`, and `ai workflows`.
- **FACT:** it receives no primary category bonus, no secondary category bonus, no domain tag bonus, and no profile bonus.
- **FACT:** its exact lexical matches are `build` and `prompt`; `prompt` is introduced by the `PROMPT_ENGINEERING` prior skill.
- **FACT:** it receives a level bonus of `12` and a production bonus of `7`, for a total of `23.7368`.
- **FACT:** `_select_courses()` rejects only later candidates with score `<18`; Agentic AI is above that floor.
- **TEST RESULT:** when supplied among exactly the reported eight candidates, it becomes Stage 8.
- **UNVERIFIED:** whether it entered the reported run from Qdrant, SQL fallback, or another unavailable prior candidate set.
- **INFERENCE:** its appearance is a tail-composition failure enabled by the eight-slot target and absent domain validator, not evidence that the current learning-path chat model selected it; no chat model is called here.

## Prior-skill ablation

These are controlled in-memory deterministic/fallback diagnostics. They are not exact Qdrant ablations because the semantic call was unavailable.

| Scenario | FastAPI rank | Agentic rank | FastAPI score | Agentic score | Selected-course effect |
|---|---:|---:|---:|---:|---|
| Exact skills | 1 | 9 | 54.8421 | 23.7368 | 5 broad Web, 2 UI/UX, 1 supporting in fallback diagnostic |
| No prior skills | 1 | 10 | 52.6429 | 22.2143 | 5 broad Web, 2 UI/UX, 1 supporting |
| No Python | 1 | 9 | 53.0000 | 24.0000 | 5 broad Web, 2 UI/UX, 1 supporting |
| No APIs | 1 | 9 | 53.0000 | 24.0000 | 5 broad Web, 2 UI/UX, 1 supporting |
| No Prompt Engineering | 1 | 10 | 56.2353 | 21.6471 | 5 broad Web, 3 UI/UX |

**Interpretation:** Python raises FastAPI's measured score by `1.8421` versus the no-Python variant; APIs has the same net delta in this token-normalized formula. Prompt Engineering raises Agentic's measured score by `2.0895` versus no Prompt Engineering. These are net changes from the denominator and shared token set, not isolated additive causal weights. Removing Prompt Engineering also raises FastAPI because fewer explicit tokens increase its normalized overlap. The exact query still does not include these skills in its first four terms.

## Goal ablation

| Scenario | Retrieval query change | FastAPI rank | Agentic rank | Result |
|---|---|---:|---:|---|
| Both displayed goals | query contains only `Build a production application` | 1 | 9 | same fallback diagnostic selection |
| Production only | same query | 1 | 9 | same |
| Advanced only | query contains `Understand advanced concepts` | 1 | 10 | same primary/secondary shape |

The baseline and production-only queries are identical because the current path pipeline reads only `goals[0]`. The second displayed goal is accepted and persisted, but it does not currently affect profile generation or `_score()`.

## Behavioral profile ablation

**FACT:** behavior profiles exist in the database and contain aggregate categories, tags, and search terms.  
**FACT:** exact screenshot identity cannot be established because its path row is absent.  
**TEST RESULT:** merging a representative stored Frontend/Extended profile changes the retrieval profile and SQL fallback candidate pool, but the production path passes a path-only profile to `_select_courses()`, so it adds no direct deterministic score component.

The representative stored profile was strongly weighted toward UI/UX, Agentic AI, Python, and evaluation/agent tags. This makes behavior a plausible candidate-pool influence, but not a verified cause of the screenshot sequence. Exact behavior/Qdrant deltas are **UNVERIFIED**.

## Taxonomy audit

**FACT — `app/schemas/learning_path.py:DOMAIN_OPTIONS`:**

| Path domain | Catalog categories | Tags |
|---|---|---|
| Frontend (`FRONTEND`) | `Web Development` | `frontend`, `ui` |
| Backend (`BACKEND`) | `Web Development` | `backend`, `apis`, `python` |
| Full-stack (`FULLSTACK`) | `Web Development` | `full-stack`, `apis` |
| API (`API`) | `Web Development` | `apis`, `async` |
| Mobile (`MOBILE`) | `Web Development` | `mobile` |
| UI/UX (`UX`) | `UI/UX Design` | `design`, `ux` |

This is a confirmed taxonomy collision. The primary category bonus distinguishes none of the five Development domains above. Only the tag bonus can distinguish them, and the reported FastAPI course has no overlap with the frontend tags `frontend` or `ui`.

## Catalog coverage and domain alignment

**FACT:** the active catalog has `60` courses, including `6` in `Web Development` and `4` in `UI/UX Design`. There are enough category-aligned courses in the full active catalog to fill eight slots without Agentic AI, although the exact semantic candidate pool is unavailable.

Using current category/tag metadata:

- primary-category matches: `6`
- secondary-category matches: `4`
- cross-category matches: `0`
- other supporting/general courses: `38`
- clearly unrelated by this audit's conservative metadata rule: `12`

For the reported eight, the measured metadata composition is:

| Stage | Course | Code-category classification | Semantic role note |
|---:|---|---|---|
| 1 | FastAPI Backend Development | primary by broad `Web Development` category | backend/API-specific; taxonomy says frontend |
| 2 | Building Real-Time Web Apps with WebSockets | primary by broad category | mixed frontend/backend content |
| 3 | Web Performance Optimization Masterclass | primary | frontend/web aligned |
| 4 | Next.js Fullstack Architecture | primary by broad category | full-stack-specific |
| 5 | Accessible Interface Craft | secondary | UI/UX aligned |
| 6 | Design Systems That Scale | secondary | UI/UX aligned |
| 7 | Design Systems for Enterprise Apps | secondary | UI/UX aligned |
| 8 | Introduction to Agentic AI | out-of-domain | no explicit Frontend/UI/UX category or tag |

Strict current-category counts are therefore `4/8` primary, `3/8` secondary, `7/8` aligned to either broad category, `0/8` cross-category, `0/8` supporting, and `1/8` out-of-domain. The more meaningful semantic drift is that three of the four primary-category items are backend/full-stack/general Web Development rather than frontend-specific.

## Difficulty and path-size effects

### Reported-eight difficulty sequence

```text
INTERMEDIATE -> INTERMEDIATE -> ADVANCED -> INTERMEDIATE ->
BEGINNER -> INTERMEDIATE -> INTERMEDIATE -> BEGINNER
```

Numeric values are `BEGINNER=0`, `INTERMEDIATE=1`, `ADVANCED=2`. The sequence contains `ADVANCED -> INTERMEDIATE`, `INTERMEDIATE -> BEGINNER`, and a final `INTERMEDIATE -> BEGINNER` regression.

**FACT:** difficulty is a score component and an ascending tie-breaker.  
**FACT:** difficulty is not a hard progression constraint.  
**TEST RESULT:** the current selector allows advanced courses before beginner courses.

### Controlled path-size diagnostic

Using the exact input and current SQL fallback candidate construction (not Qdrant):

| Scenario | Selected shape | Primary-category | Secondary-category | Supporting | Out-of-domain |
|---|---|---:|---:|---:|---:|
| Focused, 3–4 | 4 courses, all broad Web Development | 4 | 0 | 0 | 0 |
| Balanced, 6–7 | 5 broad Web + 2 UI/UX | 5 | 2 | 0 | 0 |
| Deep, 8 | 5 broad Web + 2 UI/UX + Threat Modeling | 5 | 2 | 1 | 0 |

**INFERENCE:** drift increases as the selector must fill more slots, but the measurement is fallback-only. The full catalog is not intrinsically too small; candidate-pool composition and lack of composition validation are the stronger explanations.

## Transition explanation logic

**FACT — `app/services/learning_path_service.py:_next_text()`:** transition text is a deterministic f-string: “The skills from this course provide a base for {next_course.title}...” It does not inspect tags, categories, prerequisite continuity, or semantic similarity.

**FACT:** `_reason()` similarly describes the already-selected course using its metadata and the primary domain label.

**Conclusion:** transition text does not cause selection. It rationalizes the sequence after `_select_courses()` has already chosen it. The `Design Systems for Enterprise Apps -> Introduction to Agentic AI` explanation, if persisted for the reported path, would be a post-selection generic statement rather than evidence of a semantic continuity check.

## Current validation and repair audit

| Validation | Current behavior |
|---|---|
| Course exists / SQL reload | YES, retrieval reloads active IDs from SQL |
| Course active | YES |
| Duplicate course | YES, chosen IDs are excluded during selection |
| Budget | YES, applied during selection |
| Requested count / path bound | YES, bounds are applied |
| Availability | PARTIAL; active flag only |
| Difficulty fit | PARTIAL; score component only |
| Domain alignment | NO |
| Goal alignment | NO hard validation |
| Semantic continuity | NO |
| Path progression | NO hard validation |
| Minimum count | PARTIAL; returns fewer than minimum rather than repairing |

`Introduction to Agentic AI` would not be rejected for being outside Frontend/UI/UX because no such validator exists. It is active, not duplicate, within the flexible budget, above the `18` score floor, and within the target count.

There is no learning-path generation repair loop. `create_learning_path()` selects once and persists once. The separate `replace_item()` endpoint is a user-triggered replacement flow, not an automatic domain/difficulty repair loop. Recommendation repair code in `app/agents/recommendation_graph.py` belongs to the recommendation graph and is not called by learning-path generation.

## First point of drift

```text
Questionnaire parsing       -> CORRECT; exact labels map to supported codes
Pydantic normalization      -> CORRECT; exact object validates
Profile transformation     -> BROADENING; FRONTEND becomes Web Development
Embedding query             -> BROADENING query; exact query verified, semantic result blocked
Qdrant results              -> UNVERIFIED; embedding call timed out
Deterministic ranking       -> DOMAIN DRIFT VERIFIED; +25 broad category bonus
Selection                   -> TAIL DRIFT ENABLED; score floor is 18, no composition rule
Validation                  -> DOES NOT CATCH domain or progression drift
Persistence                 -> PERSISTS whatever selection returned
```

**FIRST MEASURABLE POINT OF DOMAIN DRIFT:** the domain-to-category projection in `_profile_for_input()` and the corresponding category test in `_score()`. It is not an input parsing error; it is a lossy taxonomy representation that becomes selection-causing when the primary category bonus is applied.

## Root-cause attribution

### ROOT CAUSE #1 — taxonomy collision and broad primary category bonus

- Description: Frontend, Backend, Full-stack, Mobile, and API all share `Web Development`; frontend receives `+25` for every Web Development course.
- Evidence: `app/schemas/learning_path.py:24-29`; `app/services/learning_path_service.py:58-62`.
- Observed value: FastAPI category contribution `25`, frontend tag contribution `0`.
- Affected stage: profile projection and deterministic ranking.
- Impact: FastAPI outranks UI/UX-specific courses despite backend-oriented title/tags.
- Confidence: **HIGH**.

### ROOT CAUSE #2 — semantic order is discarded

- Description: `_select_courses()` sorts by `_score()` and does not read `semantic_score`.
- Evidence: `app/services/learning_path_service.py:112-131`.
- Observed value: controlled reported-eight set deterministically reproduces the reported order; Qdrant rank itself is unavailable.
- Affected stage: deterministic ranking.
- Impact: any semantic ordering improvement can be lost before selection.
- Confidence: **HIGH** for code behavior; **MEDIUM** for the specific historical run's rank movement.

### ROOT CAUSE #3 — no domain-composition validator or repair loop

- Description: selection checks active/duplicate/budget/count constraints but never checks explicit-domain composition or semantic continuity.
- Evidence: `app/services/learning_path_service.py:74-131,158-216`.
- Observed value: Agentic score `23.7368` exceeds the `18` tail floor and is accepted in the reported-eight set.
- Affected stage: eligibility and persistence.
- Impact: out-of-domain tail items can survive.
- Confidence: **HIGH**.

### ROOT CAUSE #4 — long-path tail exposure

- Description: eight slots force the selector to consider lower-ranked candidates; focused fallback output is fully broad-Web, while deep fallback adds supporting material.
- Evidence: `_path_bounds()` and controlled path-size diagnostic.
- Observed value: deep fallback selected one supporting course; reported-eight set includes one Agentic out-of-domain item.
- Affected stage: path length and selection.
- Impact: increases drift opportunity; does not alone identify Agentic's historical retrieval source.
- Confidence: **MEDIUM**.

### ROOT CAUSE #5 — lexical prior-skill normalization

- Description: prior skills are unioned into the explicit token set; the token term is normalized by total explicit-token count, so removing a skill can increase unrelated course scores.
- Evidence: `_score()` lines 54-57 and prior-skill ablations.
- Observed value: FastAPI `54.8421` with Python vs `53.0000` without Python; no Prompt Engineering raises FastAPI to `56.2353` while lowering Agentic to `21.6471`.
- Affected stage: deterministic scoring.
- Impact: unstable cross-domain lexical effects; not a standalone explanation for the sequence.
- Confidence: **MEDIUM**.

### Causes not established

- Qdrant semantic rank/order for the historical run: **UNVERIFIED**.
- Exact learner behavior influence for the historical run: **UNVERIFIED**.
- Catalog scarcity as a global cause: **not supported**; the active catalog has 10 Frontend/UI/UX category rows. Candidate-pool scarcity remains possible.

## Disproven or ruled-out hypotheses

- **Chat Mesh model selected the courses — NO.** The learning-path service never calls `mesh_chat_service.generate_json()`.
- **Chat Mesh model sequenced the path — NO.** Sequence is the list order emitted by `_select_courses()`.
- **Transition explanations caused Agentic AI — NO.** `_next_text()` runs after selection and only interpolates titles.
- **Basic form code mapping caused FastAPI — NO.** Exact labels map to `FRONTEND`, `UX`, `PRODUCTION`, `ADVANCED`, `FAMILIAR`, and the listed skill/format codes.
- **Budget handling caused the reported drift — NO evidence.** The exact input is flexible-budget and the controlled selector applies no price ceiling.
- **Path-count parsing alone caused the eight-item result — NO.** The UI hidden count is `4`, but `EXTENDED` independently yields bounds `(8,8)`; this is a real observability mismatch, not the domain cause.
- **Persistence changed the order — NO.** Persistence writes the already-selected list in position order; it does not rerank.

SQL fallback and Qdrant retrieval cannot be disproven as historical causes. Qdrant was not observable in this environment, and the nearest persisted path used SQL fallback.

## Observability gaps

The current path generation record stores only candidate count, selected count, fallback flags, and the final path. It does not store:

- exact retrieval query;
- candidate IDs with semantic ranks/scores;
- per-component deterministic score breakdown;
- pre- and post-rerank positions;
- domain classification or validator decisions;
- the profile snapshot used for retrieval;
- whether a candidate was added by fallback or candidate filling;
- a path-generation trace ID;
- a reason for accepting an out-of-domain tail candidate.

These gaps are why the historical screenshot cannot be reconstructed conclusively from the current row set.

## Final diagnosis

For the exact Frontend + UI/UX input, form parsing and schema validation are correct. The first verified loss of specificity is the taxonomy projection of Frontend to the broad `Web Development` category. Deterministic reranking then gives FastAPI the same full primary category bonus as frontend courses, adds lexical matches for `apis`, `python`, and `build`, and ranks it first. Qdrant semantic ordering, if present, is discarded by `_select_courses()`.

Agentic AI is not selected by a chat model. It has no explicit-domain bonus, but its lexical/level/production score is `23.7368`, above the selector's `18` tail floor. On the exact reported-eight candidate set, it becomes Stage 8. Its historical retrieval source and semantic rank remain unverified because the exact embedding/Qdrant read timed out. The absence of final domain composition and progression validation permits the resulting sequence to persist.

## Future remediation directions — no implementation in this audit

- **Taxonomy:** preserve frontend/backend/full-stack/API specificity separately from broad catalog categories.
- **Retrieval:** retain exact query, candidate provenance, semantic rank, and semantic score for each run.
- **Ranking:** keep semantic relevance visible during reranking and separate positive prior-skill signals from domain intent.
- **Path composition:** enforce explicit primary/secondary/out-of-domain composition and a minimum relevance floor.
- **Difficulty sequencing:** validate or constrain stage transitions rather than using difficulty only as a tie-breaker/score component.
- **Validation:** reject or repair out-of-domain and semantically discontinuous candidates before persistence.
- **Testing:** add a regression fixture for this exact questionnaire and the reported eight-course failure once implementation work is authorized.

## Appendix: commands and validation

Read-only searches and graph trace:

```bash
graphify query "Trace the exact SmartReco learning-path flow from questionnaire parsing through LearningPathInput normalization, profile generation, semantic/Qdrant retrieval, deterministic _score/_select_courses ranking, validation, sequencing, and persistence."
rg -n "DOMAIN_OPTIONS|DOMAIN_BY_CODE|_raw_form|_profile_for_input|build_retrieval_query|_score|_select_courses|used_mesh|generate_json|LearningPath" app tests
```

Read-only state checks:

```bash
./.venv311/bin/python - <<'PY'
# sqlite3 connection used: file:smartreco.db?mode=ro
# inspected learning_paths, learning_path_items, generation runs,
# courses, and user_interest_profiles
PY
```

Bounded semantic/Qdrant attempt:

```bash
timeout 12 ./.venv311/bin/python ...
```

Existing focused validation:

```text
./.venv311/bin/python -m pytest tests/test_path_builder.py
5 passed, 1 warning in 0.04s
```

Worktree verification after the audit showed only the pre-existing edits in `app/config.py` and `tests/test_config_validation.py`; this audit added only the two files under `docs/audits/`.

