# SmartReco Implementation Plan & Status

## Completed Tasks

### Phase 1: Foundation & Data Quality (Completed)
- Event schema with `event_id`, `schema_version`, `page_path`, `occurred_at`.
- Client-side tracker with batched `/api/events/batch` submission and beacon fallback.
- Qdrant integration with outbox pattern for async vector indexing.
- Vector reconciliation script for automated state sync.

### Phase 2: Personalization & Recommendations (Completed)
- Mesh-based recommendation workflow (`generate_recommendations`).
- Contextual related courses component (`/courses/{slug}`) with fallback ranker.
- Diagnostic admin view for recommendation runs and vector store health.
- Full test suite passing.

### Phase 3: Detailed Course Content, Curriculum & Unique Images (Completed)
- Database Schema Expansion (`0005_course_content.py`).
- 30 unique, non-repeated course cover images in `app/static/images/courses/`.
- 13 comprehensive sections on course detail pages.

### Dynamic Floating Real-Time Activity Feed Component (Completed)
- **Global Floating Overlay Widget**:
  - Implemented `app/static/js/floating-activity.js` loaded globally across all pages (`base.html`).
  - Styled with modern glassmorphic card UI, pulsing live indicator (`.live-pulse-dot`), minimize (`—`/`□`), close (`✕`), and launcher floating button.
- **Interactive Drag & Resize Capabilities**:
  - Full mouse & touch dragging support by grabbing the header handle (`#activity-drag-handle`) with window boundary constraint checking.
  - Multi-axis resizing support (`.activity-resize-handle`) with custom width/height constraints.
  - Position, size, and minimization states automatically persisted in `localStorage`.
- **Real-Time Activity Stream**:
  - Created GET `/api/events/recent` endpoint in `app/routers/events.py` returning real-time recently viewed courses, categories, dwell time, and timestamps.
  - Client-side auto-polling every 3 seconds + instant update trigger on local client event tracking (`smartreco:event_tracked`).
- **Account & Recommendations Layout Clean-up**:
  - Removed static "Recently viewed courses" panel from `app/templates/account/index.html`.
  - Removed "Email digest" section completely from `app/templates/account/recommendations.html`.
- **Test Suite Verification**:
  - All 104 tests passing in pytest.

### Phase 4: Demo commerce and access entitlements (Completed)
- Added migration `0006_commerce` with persistent carts, cart items, orders, order snapshots, and unique course entitlements.
- Existing enrollment rows receive idempotent `LEGACY_ENROLLMENT` entitlements; no learner access is removed.
- Cart and checkout use current SQL prices and `Decimal`, while order items preserve accepted title, price, and currency snapshots.
- Demo checkout grants access without collecting real payment data. Purchase grants access; starting creates enrollment.
- Catalog, detail, related, featured, and recommendation cards use one context-sensitive action state service.

### Phase 5: Explainable recommendation feedback (Completed)
- Added `0007_recommendation_feedback` with user-scoped, idempotent reason feedback linked to the original run/item/course.
- “Not for me” now opens an accessible radio selector; non-JavaScript form submission remains supported.
- Rejection feedback updates the bounded interest profile and deterministic rank adjustments, while the current view filters the rejected course immediately.
- A feedback replacement preserves the other visible recommendations and selects one active, unowned SQL candidate with deterministic grounded copy; historical runs remain intact for diagnostics.
- Mesh receives only bounded preference summaries and no optional comments or raw event history.

### Phase 6: Google OIDC authentication (Completed)
- Added optional server-side Google authorization-code login with state, nonce, PKCE S256, exact configured redirect URI, discovery metadata, rotating JWKS, and verified ID-token claims.
- Added provider-independent `external_identities` keyed by `(provider, provider_subject)` and linked existing normalized-email regular users without duplicating their carts, enrollments, recommendations, events, or learning paths.
- Google-created users use the existing `USER` role, nullable password hashes, and the normal SmartReco session; admin accounts remain password-authenticated.
- Added migration `0010_google_external_identities`, login/registration/account UI, sanitized auth events, and mocked-provider coverage without changing recommendation, commerce, enrollment, Mesh, or Qdrant flows.
