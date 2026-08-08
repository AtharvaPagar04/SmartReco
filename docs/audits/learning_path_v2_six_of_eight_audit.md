# SmartReco V2 6-of-8 Learning Path Exact Count / Mesh Lifecycle Forensic Audit

**Audit Date:** August 8, 2026  
**Mode:** READ-ONLY Forensic Audit (No code, database, Qdrant, or test modifications)  
**Target Application:** SmartReco Learning Path V2 Pipeline  

---

## 1. Executive Summary

A forensic audit was performed to investigate why a user request for a **Deep path (8 courses / EXTENDED)** yielded a persisted and rendered page containing only **6 courses** (~17 hours, ~4 weeks, USD 307.00) with generic/template-like explanation text containing internal enum copy such as `"cross_domain"`.

### Key Findings
1. **Primary Cause — Candidate Shortage:** Out of the 60 active courses in the catalog, **exactly 6 courses** satisfy domain affinity thresholds ($\ge 0.25$) for Primary = `FRONTEND` and Secondary = `UX`. There are 2 `PRIMARY`, 2 `SECONDARY`, 2 `CROSS_DOMAIN`, and 0 `SUPPORTING` courses. 54 courses are `OUT_OF_DOMAIN`. It is **physically impossible** to construct a valid 8-course domain-safe path for Frontend + UX with the current catalog.
2. **Mesh Planner Failure & Repair Exhaustion:** If Mesh was invoked, any 8-course plan it generated necessarily included at least 2 `OUT_OF_DOMAIN` courses. The strict validator (`exact_count=True`) rejected Mesh's plan, triggering repair. Bounded repair failed for the same catalog constraint, causing `generate_plan_with_repairs` to enter deterministic fallback.
3. **Fallback Truncation & Validation Bypass:** `select_fallback_courses()` filtered out all `OUT_OF_DOMAIN` candidates, collecting all 6 available domain-safe courses. `generate_plan_with_repairs()` then called `validate_learning_path_plan(..., exact_count=False)` with `exact_count=False` for fallback. The 6-course plan passed validation with `validation_status = "FALLBACK_VALID"`.
4. **Persistence Gate Omission:** `create_learning_path()` persisted the 6-course plan to SQLite and set status to `"READY"` without asserting `len(courses) == intent.requested_course_count`.
5. **Generic Wording & Enum Leakage:** The displayed course explanations were produced by `fallback_plan()` using static template strings. Line 231 of `learning_path_planner.py` directly interpolates `role.casefold()`, causing raw enum strings like `"cross_domain"` to leak into user-facing text.

---

## 2. Exact Run Identification & UI vs Database Verification

### Database vs UI Audit
- **DB Item Count:** 6
- **Rendered Item Count:** 6
- **Hidden / Inactive Rows:** None
- **Pagination / Slicing:** None
- **Verdict:** UI rendering is **100% accurate** to database state. There is no presentation bug.

### Course Sequence Metrics ($307.00, 17 Hours)
| Position | Course Title | Category | Role | Price (USD) | Duration (min) | Hours | Difficulty |
|---:|---|---|---|---:|---:|---:|---|
| 1 | Design Systems for Enterprise Apps | UI/UX Design | CROSS_DOMAIN | $65.00 | 180 | 3 | INTERMEDIATE |
| 2 | Web Performance Optimization Masterclass | Web Development | PRIMARY | $59.00 | 180 | 3 | ADVANCED |
| 3 | Advanced Motion Design for Web Interfaces | UI/UX Design | CROSS_DOMAIN | $55.00 | 160 | 3 | ADVANCED |
| 4 | Next.js Fullstack Architecture | Web Development | PRIMARY | $79.00 | 240 | 4 | INTERMEDIATE |
| 5 | Accessible Interface Craft | UI/UX Design | SECONDARY | $0.00 | 120 | 2 | BEGINNER |
| 6 | Design Systems That Scale | UI/UX Design | SECONDARY | $49.00 | 140 | 2 | INTERMEDIATE |
| **Total** | | | | **$307.00** | **1020** | **17** | |

Calculated weeks at 5 hours/week: $\lceil 17 / 5 \rceil = 4$ weeks.

---

## 3. Exact Count Lifecycle Trace

| Stage | `path_length` | `requested_course_count` | Resolved Target Count | Enforced? | Result |
|---|---|---:|---:|---|---|
| Browser Form | Deep path (8) | 8 | 8 | Yes | 8 |
| Parsed Input | EXTENDED | 8 | 8 | Yes | 8 |
| Pydantic Schema | EXTENDED | 8 | 8 | Yes | 8 |
| Canonical Intent | EXTENDED | 8 | 8 | Yes | 8 |
| Retrieval | EXTENDED | 8 | 19 candidates retrieved | Yes | 19 (only 6 domain-safe) |
| Planner Prompt | EXTENDED | 8 | 8 | Yes | Prompt asks for 8 |
| Validator (Mesh) | EXTENDED | 8 | 8 | Yes (`exact_count=True`) | **FAILED** (OUT_OF_DOMAIN courses) |
| Repair Loop | EXTENDED | 8 | 8 | Yes (`exact_count=True`) | **FAILED** (Cannot fix scarcity) |
| **Fallback Selection** | EXTENDED | 8 | **6** | **NO** (Stopped at max available) | **6 (First Count Reduction)** |
| **Fallback Validator** | EXTENDED | 8 | **6** | **NO** (`exact_count=False` passed) | Passed (`FALLBACK_VALID`) |
| **Persistence Gate** | EXTENDED | 8 | **6** | **NO** (No invariant check) | Persisted 6 items as `READY` |
| UI Render | EXTENDED | 8 | **6** | N/A | Renders 6 DB items |

---

## 4. Deep / Extended Policy Audit

- Policy mapping in `learning_path_policy.py`:
  - `FOCUSED` $\rightarrow 4$ courses
  - `BALANCED` $\rightarrow 7$ courses
  - `EXTENDED` / `DEEP` $\rightarrow 8$ courses
  - `AUTO` $\rightarrow 4, 7,$ or $8$ based on `requested_course_count`
- Composition Policy for `EXTENDED` with secondary domain:
  - `min_primary`: 4
  - `min_secondary`: 2
  - `max_supporting`: 2
  - `max_out_of_domain`: 0
- Invariant Requirement: The policy requires **exactly 8** courses for `EXTENDED`/`DEEP`. However, `select_fallback_courses()` and `generate_plan_with_repairs()` allow fallback to bypass this count invariant.

---

## 5. Candidate Pool & Catalog Exhaustion Reconstruction

### Candidate Pool Classification (Primary: FRONTEND, Secondary: UX)
Out of 60 active courses in `smartreco.db`:
- `PRIMARY` ($\ge 0.50$ Frontend affinity): **2 courses**
  - Web Performance Optimization Masterclass (0.94)
  - Next.js Fullstack Architecture (0.76)
- `SECONDARY` ($\ge 0.50$ UX affinity): **2 courses**
  - Accessible Interface Craft (1.00)
  - Design Systems That Scale (0.98)
- `CROSS_DOMAIN` ($\ge 0.72$ Frontend AND $\ge 0.72$ UX): **2 courses**
  - Advanced Motion Design for Web Interfaces (Front: 0.94, UX: 1.00)
  - Design Systems for Enterprise Apps (Front: 0.92, UX: 1.00)
- `SUPPORTING` ($0.25 \le \text{affinity} < 0.50$): **0 courses**
- `OUT_OF_DOMAIN` ($\text{affinity} < 0.25$): **54 courses**

### Candidate Shortage Proof
- Total domain-safe candidates in entire catalog: **6**
- Total requested for Deep path: **8**
- **Conclusion:** Candidate shortage is **PROVEN**. An 8-course valid domain-safe path cannot be constructed without adding new courses or relaxing classification thresholds.

---

## 6. Mesh Planner, Repair, & Fallback Lifecycle Audit

### 1. Mesh Planner
- Invoked: Yes (`generate_learning_path_json` in `generate_plan_with_repairs`)
- Model: `deepseek/deepseek-v4-flash`
- Prompt: Explicitly requests 8 courses.
- Schema: JSON schema enforces `stages` array with `min_length=1`, `max_length=8`. Pydantic does **not** enforce exact length of 8 in schema validation alone.
- Outcome: Mesh either returned 8 courses (including `OUT_OF_DOMAIN` courses) or failed/timed out. Validation rejected the output (`OUT_OF_DOMAIN` violation).

### 2. Repair Loop
- Max repairs: 1 attempt.
- Outcome: Repair could not resolve the catalog shortage of domain-safe courses.

### 3. Deterministic Fallback
- Function: `select_fallback_courses()` in `learning_path_planner.py`
- Algorithm: Filters out `ROLE_OUT_OF_DOMAIN` candidates and selects up to `requested_course_count` matching primary, secondary, and supporting limits.
- Failure Mode: When only 6 domain-safe courses exist, `select_fallback_courses()` returns all 6 and stops without raising an error.
- Plan Wrapping: `fallback_plan()` constructs a 6-stage `LearningPathPlan`.
- Validation: `generate_plan_with_repairs()` runs `validate_learning_path_plan(plan.model_dump(), intent, ranked, exact_count=False)`. Passing `exact_count=False` causes validation to succeed with `validation_status = "FALLBACK_VALID"`.

---

## 7. Persistence Gate & Status Lifecycle Audit

- Code location: `app/services/learning_path_service.py` (`create_learning_path`)
- Status set: `"READY"`
- Invariant check: **NONE**. `create_learning_path` accepts `plan_result`, reloads `courses`, calculates total minutes/hours/price, writes `LearningPathItem` rows for the returned courses, and marks the path status as `"READY"`.
- Flaw: There is no assertion `len(courses) == intent.requested_course_count` before persisting. Partial/truncated fallback paths are saved as `READY`.

---

## 8. Explanation Provenance & Internal Wording Leakage Audit

### Explanation Text Source
- `why_this_course`: Generated by `fallback_plan()` (line 231 of `learning_path_planner.py`).
  - Template: `f"This {role.casefold()} stage supports {', '.join(intent.goal_labels)} through {skills}."`
  - Rendered: `"This cross_domain stage supports Build a production application, Understand advanced concepts through Structure design tokens..."`
- `how_it_leads_forward`: Generated by `fallback_plan()` (line 234 of `learning_path_planner.py`).
  - Template: `f"It prepares the learner for {next_title} using the selected catalog sequence."`

### Enum Leakage Diagnosis
- **Interpolation Leakage:** `role.casefold()` directly injects the internal string `"cross_domain"`, `"primary"`, or `"secondary"` into user-facing copy.

---

## 9. Ordering, Difficulty, & Goal Coverage Audit

### Course Sequence & Rationale
1. **Design Systems for Enterprise Apps** (CROSS_DOMAIN, INTERMEDIATE)
2. **Web Performance Optimization Masterclass** (PRIMARY, ADVANCED)
3. **Advanced Motion Design for Web Interfaces** (CROSS_DOMAIN, ADVANCED)
4. **Next.js Fullstack Architecture** (PRIMARY, INTERMEDIATE)
5. **Accessible Interface Craft** (SECONDARY, BEGINNER)
6. **Design Systems That Scale** (SECONDARY, INTERMEDIATE)

- **Source of Order:** `select_fallback_courses()` algorithm (adds Primary/Cross items up to `min_primary`, then remaining secondary items).
- **Difficulty Validation:** Passes (`INTERMEDIATE` $\rightarrow$ `ADVANCED` $\rightarrow$ `ADVANCED` $\rightarrow$ `INTERMEDIATE` $\rightarrow$ `BEGINNER` $\rightarrow$ `INTERMEDIATE`). No step regresses by $\ge 2$ difficulty tiers without domain justification.
- **Goal Coverage:** Both learner goals (`PRODUCTION` and `ADVANCED`) are assigned across the stages.

---

## 10. Generation Provenance Metadata

Exact metadata recorded for this run in `metadata_json` of `LearningPathGenerationRun`:
- `semantic_retrieval_used`: `true`
- `sql_fallback_used`: `false`
- `llm_generation_used`: `false`
- `llm_repair_count`: 1
- `deterministic_fallback_used`: `true`
- `generation_model`: `null`
- `validation_status`: `"FALLBACK_VALID"`
- `candidate_count`: 19
- `selected_count`: 6
- `target_count`: 8

---

## 11. Root Causes Ranked

### ROOT CAUSE #1
- **Description:** Candidate Scarcity for Frontend + UX Domain Combination.
- **Evidence:** Only 6 active courses out of 60 in `smartreco.db` satisfy `primary_affinity >= 0.50` or `secondary_affinity >= 0.50`. 0 courses satisfy `0.25 <= affinity < 0.50`.
- **File:** `app/services/learning_path_policy.py`
- **Function:** `classify_course_domain_affinity`
- **Impact:** An 8-course valid domain-safe path cannot be generated.

### ROOT CAUSE #2
- **Description:** Exact-Count Invariant Bypass in Fallback Validation.
- **Evidence:** `generate_plan_with_repairs()` line 279 calls `validate_learning_path_plan(..., exact_count=False)`.
- **File:** `app/services/learning_path_planner.py`
- **Function:** `generate_plan_with_repairs`
- **Impact:** Truncated fallback paths (6 courses) receive `"FALLBACK_VALID"` status instead of `"INSUFFICIENT_COVERAGE"`.

### ROOT CAUSE #3
- **Description:** Missing Post-Condition Assertion at Persistence Gate.
- **Evidence:** `create_learning_path()` persists whatever `plan_result` provides without verifying `len(courses) == intent.requested_course_count`.
- **File:** `app/services/learning_path_service.py`
- **Function:** `create_learning_path`
- **Impact:** Partial/truncated paths are saved with status `"READY"`.

### ROOT CAUSE #4
- **Description:** Internal Enum Leakage in Deterministic Fallback Copy.
- **Evidence:** `why_this_course = f"This {role.casefold()} stage supports..."` in `fallback_plan()`.
- **File:** `app/services/learning_path_planner.py`
- **Function:** `fallback_plan`
- **Impact:** Raw internal enum strings (`cross_domain`) are displayed in user copy.

---

## 12. Disproven Hypotheses

- **Migration 0011 corruption:** Disproven. Schema is valid and metadata columns exist.
- **UI presentation / rendering bug:** Disproven. DB contains exactly 6 items; UI faithfully renders all 6.
- **Mesh returning 6 valid courses:** Disproven. Mesh either failed or returned ungrounded/out-of-domain courses rejected by validation.
- **Budget constraint truncation:** Disproven. Total price is $307.00 under a FLEXIBLE budget.
- **Difficulty regression filtering:** Disproven. Difficulty validator passed all 6 courses.

---

## 13. Missing Regression Tests

1. Test asserting that `select_fallback_courses()` returns insufficient status or raises when candidate pool contains fewer domain-safe candidates than `requested_course_count`.
2. Test asserting that `generate_plan_with_repairs()` sets `validation_status = "INSUFFICIENT_COVERAGE"` when fallback cannot satisfy exact count.
3. Test asserting that `create_learning_path()` does not persist status `"READY"` when `len(courses) != requested_course_count`.
4. Test asserting that fallback `why_this_course` text does not contain raw enum strings like `cross_domain`.
5. Test evaluating catalog coverage across all supported primary + secondary domain pairs for `EXTENDED` (8-course) requests.

---

## 14. Remediation Directions — NO IMPLEMENTATION

1. **Catalog Expansion / Domain Classification Adjustment:** Add courses or refine `classify_course_domain_affinity` thresholds so `SUPPORTING` tier includes adjacent domain topics when primary/secondary candidates are exhausted.
2. **Strict Fallback Validation:** Update `generate_plan_with_repairs()` to enforce `exact_count=True` during fallback validation or set status to `"INSUFFICIENT_COVERAGE"` when count is not met.
3. **Persistence Gate Invariant:** Add an explicit assertion in `create_learning_path()` that marks path status as `"PARTIAL"` or `"INSUFFICIENT_COVERAGE"` if `len(courses) < intent.requested_course_count`.
4. **Copy Sanitization:** Refactor `fallback_plan()` to map internal roles (`ROLE_CROSS_DOMAIN`, `ROLE_PRIMARY`) to friendly user-facing labels (e.g. `"core domain"`, `"interdisciplinary"`).
