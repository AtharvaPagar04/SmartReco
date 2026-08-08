# SmartReco Learning Path V2 Implementation

## Status

Implemented on 2026-08-08. The historical forensic record remains in `learning_path_exact_run_audit.md`; this document records the implementation that follows it.

## Architecture

The learning-path flow is now:

```text
questionnaire
  -> LearningPathIntent
  -> separate primary, secondary, goal, and preference retrieval queries
  -> Mesh embeddings / Qdrant candidate merge
  -> SQL reload and eligibility filtering
  -> domain-aware deterministic pre-ranking
  -> grounded Mesh chat planner
  -> deterministic validator
  -> one bounded Mesh repair by default
  -> deterministic domain-safe fallback
  -> SQL-authoritative persistence
```

The normal selector is no longer the old broad-category `_score()` algorithm. Deterministic selection exists only as the explicit fallback and replacement safety path. A LangGraph node graph was not added: the existing application has a recommendation-only graph, and a second decorative graph would not add control-flow value to this bounded service orchestration.

## Exact regression intent

The implementation preserves both selected goals and separates them from known skills:

| Intent | Value |
| --- | --- |
| Primary | `FRONTEND` / Frontend Development |
| Secondary | `UX` / UI/UX Design |
| Goals | `PRODUCTION`, `ADVANCED` |
| Level | `FAMILIAR` |
| Preference | `PRODUCTION` |
| Known skills | `PYTHON`, `GIT`, `APIS`, `PROMPT_ENGINEERING` |
| Formats | `PRACTICE`, `PROJECTS` |
| Weekly time | `5` |
| Path mode/count | `DEEP` / `8` |

`LearningPathInput` now derives the requested count server-side from a named path mode, so a stale hidden `requested_course_count` cannot leave an extended path persisted as four courses.

## Domain policy

`app/services/learning_path_policy.py` keeps `Course.category` unchanged and adds path-specific affinity from title, tags, descriptions, skills, prerequisites, tools, and project metadata. Broad `Web Development` is not a frontend match by itself. Backend markers such as FastAPI, Python, APIs, and server-side reduce frontend affinity; frontend markers such as React, TypeScript, browser, interfaces, and web performance increase it.

The policy emits `PRIMARY`, `SECONDARY`, `CROSS_DOMAIN`, `SUPPORTING`, or `OUT_OF_DOMAIN`. Deep paths require at least four primary-aligned courses and two secondary-aligned courses, allow at most two supporting courses, and allow zero out-of-domain courses. Focused and balanced modes use their smaller coverage policies.

## Retrieval and ranking

`retrieve_learning_path_candidates()` creates independent retrieval intents for primary domain, secondary domain, goals, and preferences/format context. It merges duplicate Qdrant hits while preserving the highest semantic score and all retrieval sources. SQL is used to fill the grounded pool and remains the authoritative source for active status, exclusions, prices, hours, and metadata.

The candidate target is `max(16, requested_course_count * 3)`. Pre-ranking retains semantic relevance and uses centralized normalized weights: semantic 35%, domain 30%, goals 15%, level 10%, preferences 5%, and bounded behavior 5%. Known-skill redundancy is a penalty/prerequisite signal, not a target-topic bonus.

## Mesh planner and grounding

`app/services/mesh_chat_service.py:generate_learning_path_json()` uses `learning_path_chat_model` when configured, otherwise the existing Mesh chat model. The structured response contains title, summary, final outcome, stage order, grounded course ID, role, selected goal codes, and personalized explanation fields.

The prompt explicitly states that current questionnaire intent outranks behavior, prior skills are already known, all selected goals must be covered, and only supplied candidate IDs may be used. Prices, duration, difficulty, taxonomy, and eligibility are reloaded from SQL after planning and are never trusted from model output.

## Validation and repair

`app/services/learning_path_validator.py` returns structured violation codes for:

- ungrounded, inactive, duplicate, excluded, or incorrectly counted courses;
- out-of-domain courses, primary/secondary coverage, and supporting-course limits;
- missing or unknown goal codes;
- free/per-course/path budget violations;
- sharp difficulty regressions and unsupported beginner returns;
- unsupported adjacent transitions;
- introductory redundancy with known skills.

Invalid structured output is sent back to Mesh with the same candidate set and the violations. `learning_path_max_repairs` defaults to one and is bounded. Invalid JSON, provider errors, timeouts, or failed repairs use a deterministic fallback that applies the same domain policy and budget checks. If the catalog cannot satisfy the requested composition, the fallback remains short rather than filling the tail with unrelated courses.

## Persistence and observability

The historical meanings of `LearningPath.used_mesh` and `LearningPath.used_fallback` are retained for compatibility: `used_mesh` still reports semantic retrieval success. Migration `0011_learning_path_v2_metadata` adds nullable `LearningPathGenerationRun.metadata_json` with:

```json
{
  "semantic_retrieval_used": true,
  "sql_fallback_used": false,
  "llm_generation_used": true,
  "llm_repair_used": false,
  "llm_repair_count": 0,
  "deterministic_fallback_used": false,
  "generation_model": "...",
  "validation_status": "VALID"
}
```

When LangSmith is enabled, the path retrieval/planning span receives only bounded metadata: path mode, requested count, domain codes/counts, goal count, candidate count, and profile version. No email, session, credential, or raw event history is traced.

## Replacement flow

Single-course replacement now reloads the same canonical input, uses V2 pre-ranking, excludes existing path courses, rejects out-of-domain candidates, and retains a deterministic neighbor-safe explanation. It does not bypass the path policy.

## Tests

`tests/test_learning_path_v2.py` covers intent separation, taxonomy collision, safe fallback composition, valid Mesh planning, all-goal prompt context, out-of-domain repair, invented IDs, and wrong count. Existing path-builder tests were updated where they encoded the previous unsafe deterministic behavior. The route regression test disables Mesh explicitly and verifies the bounded fallback persistence path.

Focused verification:

```text
tests/test_path_builder.py                         5 passed
tests/test_learning_path_v2.py                     6 passed
tests/test_learning_path_event_regression.py      route case passes; the repository's aiosqlite fixture teardown can hang on the remaining fixture in this environment
```

## Files

- `app/services/learning_path_intent.py` — canonical intent.
- `app/services/learning_path_policy.py` — affinity and composition rules.
- `app/services/learning_path_planner.py` — pre-ranking, Mesh planning, repair, and fallback.
- `app/services/learning_path_validator.py` — deterministic post-generation validation.
- `app/services/learning_path_service.py` — V2 orchestration and persistence.
- `app/services/recommendation_retrieval_service.py` — path-only multi-query retrieval additions; recommendation retrieval remains unchanged.
- `app/services/mesh_chat_service.py` — grounded path JSON call.
- `alembic/versions/0011_learning_path_v2_metadata.py` — generation provenance.
- `tests/test_learning_path_v2.py` — focused regression coverage.
