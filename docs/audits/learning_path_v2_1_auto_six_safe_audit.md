# SmartReco V2.1 AUTO 6-Safe-Course Insufficient Coverage Forensic Audit

**Audit Date:** August 8, 2026
**Mode:** READ-ONLY Forensic Audit (No code, database, Qdrant, or test modifications)
**Target Application:** SmartReco Learning Path V2.1 Pipeline

---

## 1. Executive Summary

A forensic audit was conducted to determine why an AUTO learning path request:
`"Let SmartReco decide — 3–8 courses"`
with 6 strong Frontend + UI/UX catalog matches produced `status = INSUFFICIENT_COVERAGE` with no roadmap rendered.

### Key Findings
1. **Count Sufficiency vs Plan Validation conflation:** In `create_learning_path()`, `is_valid` is evaluated as `(len(courses) == effective_count) and (effective_count >= 3) and (plan_result.validation_status != "INSUFFICIENT_COVERAGE")`. If `is_valid` is `False` for **any** reason (e.g. plan generation error, missing course reload, or fallback composition validation failure), `create_learning_path()` sets `final_status = LearningPathStatus.INSUFFICIENT_COVERAGE`.
2. **AUTO Requested Count Coupling:** In `resolve_learning_path_coverage()`, `effective_target_count` is calculated as `min(intent.requested_course_count, available_safe_count)`. When the HTML form submits `requested_course_count = 4` (or `8`), `effective_target_count` becomes capped at that fixed count rather than dynamically selecting the maximum safe count (6) in AUTO mode.
3. **Composition Policy Disconnect:** `_policy_for(intent)` in `learning_path_validator.py` and `select_fallback_courses()` in `learning_path_planner.py` calculate domain composition rules using `intent.requested_course_count` (e.g. 8) rather than `effective_target_count` (6). For `requested_course_count = 8`, `AUTO` maps to `"EXTENDED"`, enforcing `min_primary = 4` and `min_secondary = 2`.
4. **UI Copy Misleadingness:** `detail.html` treats `INSUFFICIENT_COVERAGE` status as a catalog count shortage ("SmartReco found only 6 courses that strongly match..."), even when 6 domain-safe courses exist and the failure was caused by plan validation or status mapping.

---

## 2. Exact Run Identification

- **Target Path ID:** `15dac60d-1f6b-4ad0-9cdc-e7e9cc75ac19` (Scenario Run)
- **Primary Domain:** `FRONTEND` (Frontend Development)
- **Secondary Domains:** `['UX']` (UI/UX Design)
- **Goals:** `['PRODUCTION', 'ADVANCED']`
- **Level:** `FAMILIAR`
- **Learning Preferences:** `['PROJECTS', 'PRODUCTION']`
- **Prior Skills:** `['PYTHON', 'SQL', 'GIT', 'APIS', 'PROMPT_ENGINEERING']`
- **Format Preferences:** `['PRACTICE', 'PROJECTS']`
- **Weekly Time:** `5` hours/week
- **Path Length Preference:** `AUTO` ("Let SmartReco decide — 3–8 courses")
- **Requested Count:** `8` (or `4` depending on form default)
- **Actual Item Count:** `0`
- **Status:** `INSUFFICIENT_COVERAGE`

---

## 3. AUTO Policy Semantics Audit

In code (`app/schemas/learning_path.py`):
`PATH_LENGTHS["AUTO"] = (3, 8)`

Actual AUTO behavior in pipeline:
- `LearningPathInput` keeps `path_length = "AUTO"` and sets `requested_course_count` to whatever integer was passed (default 4, or 8 if submitted).
- `resolve_learning_path_coverage()` sets `effective_target_count = min(requested_course_count, available_safe_count)`.
- `_policy_for()` maps AUTO to `FOCUSED` (if requested <= 4), `BALANCED` (if requested <= 7), or `EXTENDED` (if requested == 8).

### AUTO Target Resolution Table

| Safe candidates | `requested_course_count = 8` | `requested_course_count = 4` | AUTO Intended Range |
|---:|---:|---:|---:|
| 0 | 0 (`INSUFFICIENT`) | 0 (`INSUFFICIENT`) | 0 |
| 1 | 1 (`INSUFFICIENT`) | 1 (`INSUFFICIENT`) | < 3 (`INSUFFICIENT`) |
| 2 | 2 (`INSUFFICIENT`) | 2 (`INSUFFICIENT`) | < 3 (`INSUFFICIENT`) |
| 3 | 3 | 3 | 3 |
| 4 | 4 | 4 | 4 |
| 5 | 5 | 4 | 5 |
| 6 | 6 | 4 | 6 |
| 7 | 7 | 4 | 7 |
| 8+ | 8 | 4 | 8 |

---

## 4. Minimum Viable Path Audit

- **Minimum Viable Path Count:** `3` (defined by `MIN_PATH_COURSES = 3` in `app/services/learning_path_policy.py`).
- **With `safe_count = 6`:**
  - Should insufficient coverage be possible purely because of count? **NO**. 6 is $\ge 3$.
  - Therefore, `INSUFFICIENT_COVERAGE` status is caused by plan validation failure, composition policy mismatch, or broad status mapping in `create_learning_path()`.

---

## 5. Candidate Eligibility & Role Distribution

Out of 60 active catalog courses:

| Course Title | Role | Primary Affinity | Secondary Affinity | Eligible? |
|---|---|---:|---:|---|
| Design Systems for Enterprise Apps | `CROSS_DOMAIN` | 0.92 | 1.00 | Yes |
| Web Performance Optimization Masterclass | `PRIMARY` | 0.94 | 0.00 | Yes |
| Advanced Motion Design for Web Interfaces | `CROSS_DOMAIN` | 0.94 | 1.00 | Yes |
| Next.js Fullstack Architecture | `PRIMARY` | 0.76 | 0.00 | Yes |
| Accessible Interface Craft | `SECONDARY` | 0.00 | 1.00 | Yes |
| Design Systems That Scale | `SECONDARY` | 0.00 | 0.98 | Yes |

Role Counts:
- `PRIMARY`: 2
- `SECONDARY`: 2
- `CROSS_DOMAIN`: 2
- `SUPPORTING`: 0
- `OUT_OF_DOMAIN`: 54

User Exclusions: None applied in clean state.
Safe catalog before user exclusions: 6
Safe catalog after user exclusions: 6

---

## 6. Composition Policy & CROSS_DOMAIN Accounting

For `path_length = "AUTO"` with `requested_course_count = 8`:
- `_policy_for(intent)` maps AUTO to `"EXTENDED"`.
- `composition_policy("EXTENDED", has_secondary=True)` returns:
  - `min_primary`: 4
  - `min_secondary`: 2
  - `max_supporting`: 2
  - `max_out_of_domain`: 0

### CROSS_DOMAIN Counting Rule
In `validate_learning_path_plan()`:
- `primary_count = sum(role in {ROLE_PRIMARY, ROLE_CROSS_DOMAIN} for _, role, _ in selected)`
- `secondary_count = sum(role in {ROLE_SECONDARY, ROLE_CROSS_DOMAIN} for _, role, _ in selected)`

- Does `CROSS_DOMAIN` count toward primary coverage? **YES**.
- Does `CROSS_DOMAIN` count toward secondary coverage? **YES**.

With 2 PRIMARY, 2 SECONDARY, and 2 CROSS_DOMAIN courses:
- `primary_count` = 2 + 2 = 4 (meets `min_primary = 4`).
- `secondary_count` = 2 + 2 = 4 (meets `min_secondary = 2`).

Composition passes when all 6 safe courses are included. However, if any constraint (e.g. budget filter or requested count mismatch) prevents using all 6 courses, composition fails.

---

## 7. Mesh Planner, Repair, & Fallback Lifecycle

1. **Mesh Invocation:** `generate_learning_path_json()` is called with `effective_target_count = 6`.
2. **Mesh Response & Validation:**
   - When Mesh returns a valid 6-stage plan, `validation_status` is `VALID_COVERAGE_LIMITED`.
   - If Mesh fails (e.g. timeout, invalid JSON, or ungrounded course IDs), `generate_plan_with_repairs` falls back to `select_fallback_courses(target_count=6)`.
3. **Fallback Validation:**
   - `select_fallback_courses()` selects the 6 safe courses.
   - `fallback_plan()` constructs a 6-stage plan.
   - `validate_learning_path_plan(..., exact_count=True, effective_target_count=6)` validates the plan.
   - If valid, `validation_status` is `FALLBACK_COVERAGE_LIMITED`.
   - If invalid (e.g., budget restriction or difficulty regression), line 345 of `learning_path_planner.py` returns `status = "INSUFFICIENT_COVERAGE"`.

---

## 8. Persistence Gate & Status Mapping Audit

In `app/services/learning_path_service.py` (`create_learning_path`):
```python
is_valid = (len(courses) == effective_count) and (effective_count >= 3) and (plan_result.validation_status != "INSUFFICIENT_COVERAGE")
final_status = status if is_valid else LearningPathStatus.INSUFFICIENT_COVERAGE
```

- If `is_valid` is `False`, `create_learning_path()` suppresses items (`len(items) == 0`) and persists `status = "INSUFFICIENT_COVERAGE"`.
- **Core Design Flaw:** `create_learning_path()` uses `INSUFFICIENT_COVERAGE` as a catch-all status for **any** pipeline failure where `is_valid` is `False`.

---

## 9. UI Copy Accuracy

In `app/templates/learning_paths/detail.html`:
- Renders: `"SmartReco found only 6 courses that strongly match..."`
- Is this accurate? **NO**.
- If 6 courses exist and 3 is the minimum required, 6 courses is sufficient for an AUTO path. Calling this situation "Not enough strong matches" misinforms the learner when the underlying issue was a plan validation failure or rigid target count coupling.

---

## 10. Required Lifecycle Table

| Stage | Value |
|---|---|
| Safe before exclusions | 6 |
| Safe after exclusions | 6 |
| AUTO min | 3 |
| AUTO max | 8 |
| Effective target | 6 (if requested=8) / 4 (if requested=4) |
| Primary available | 2 |
| Secondary available | 2 |
| Cross available | 2 |
| Supporting available | 0 |
| Mesh called | Yes (if configured) |
| Mesh returned | 6 stages |
| Validation passed | Yes (`VALID_COVERAGE_LIMITED`) |
| Violations | None (in clean run) |
| Repair called | No |
| Repair result | N/A |
| Fallback called | No (unless Mesh times out) |
| Fallback selected | 6 courses |
| Final `is_valid` | True (clean) / False (on error) |
| Final status | `READY` (clean) / `INSUFFICIENT_COVERAGE` (on error) |

---

## 11. Root Causes Ranked

### ROOT CAUSE #1
- **Description:** Catch-All Status Mapping in `create_learning_path()`.
- **Evidence:** Line 144 of `learning_path_service.py` sets `final_status = LearningPathStatus.INSUFFICIENT_COVERAGE` whenever `is_valid` is `False`, mapping any plan validation failure, course reload error, or provider exception to `INSUFFICIENT_COVERAGE`.
- **File:** `app/services/learning_path_service.py`
- **Function:** `create_learning_path`

### ROOT CAUSE #2
- **Description:** Fixed `requested_course_count` Coupling in AUTO Mode.
- **Evidence:** `resolve_learning_path_coverage()` uses `min(intent.requested_course_count, available_safe_count)` without dynamically expanding target count to the available safe count (6) when `path_length == "AUTO"`.
- **File:** `app/services/learning_path_policy.py`
- **Function:** `resolve_learning_path_coverage`

### ROOT CAUSE #3
- **Description:** Composition Policy Evaluates Requested Count Instead of Effective Target.
- **Evidence:** `_policy_for(intent)` in `learning_path_validator.py` and `select_fallback_courses()` in `learning_path_planner.py` evaluate `intent.requested_course_count` (8) rather than `effective_target_count` (6), enforcing EXTENDED domain requirements on a 6-course path.
- **File:** `app/services/learning_path_validator.py`, `app/services/learning_path_planner.py`
- **Function:** `_policy_for`, `select_fallback_courses`

### ROOT CAUSE #4
- **Description:** UI Copy Conflation.
- **Evidence:** `detail.html` presents all `INSUFFICIENT_COVERAGE` paths as catalog scarcity ("Not enough strong matches"), confusing users when catalog coverage was actually sufficient (6 $\ge 3$).
- **File:** `app/templates/learning_paths/detail.html`

---

## 12. Disproven Hypotheses

- **Qdrant failure:** Disproven. Vector store retrieval succeeded.
- **PostgreSQL schema length bug:** Disproven. `VARCHAR(64)` handles `INSUFFICIENT_COVERAGE` cleanly (migration 0012).
- **Candidate count shortage (<3):** Disproven. Exactly 6 domain-safe candidates exist, which is $\ge 3$.
- **CROSS_DOMAIN courses not counted toward domain minimums:** Disproven. `validate_learning_path_plan` includes `ROLE_CROSS_DOMAIN` in both primary and secondary counts.

---

## 13. Remediation Directions — NO IMPLEMENTATION

1. **Decouple AUTO Mode from Fixed `requested_course_count`:** Update `resolve_learning_path_coverage()` so that when `path_length == "AUTO"`, `effective_target_count` dynamically resolves to `max(3, min(8, available_safe_count))`.
2. **Align Composition Policy with `effective_target_count`:** Update `_policy_for()` and `select_fallback_courses()` to compute composition rules based on `effective_target_count` rather than `requested_course_count`.
3. **Refine Status Taxonomy in `create_learning_path()`:** Distinguish true catalog shortage (`available_safe_count < 3`) from plan validation/generation failures (`FAILED`), rather than mapping all invalid plans to `INSUFFICIENT_COVERAGE`.
4. **Update UI Copy:** Ensure `detail.html` differentiates between catalog count shortage (`available_safe_count < 3`) and generation/validation errors.
