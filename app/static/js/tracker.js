(function () {
  'use strict';
  const max = 100, batchSize = 10, impressionKey = 'smartreco_recent_impressions_v1';
  const impressionTtl = 15 * 60 * 1000, relatedImpressionKey = 'smartreco_recent_related_impressions_v1', queue = [], qualified = new Set(), qualifiedRecommendations = new Set(), qualifiedRelated = new Set(), timers = new Map();
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
  let sending = false, started = performance.now(), sentDwell = false;

  function eventId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    const bytes = window.crypto?.getRandomValues ? window.crypto.getRandomValues(new Uint8Array(16)) : null;
    const raw = bytes ? Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('') : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`.padEnd(32, '0');
    return `${raw.slice(0, 8)}-${raw.slice(8, 12)}-4${raw.slice(13, 16)}-8${raw.slice(17, 20)}-${raw.slice(20, 32)}`;
  }

  const sessionKey = 'smartreco_session_id_v1', lastActivityKey = 'smartreco_last_activity_at_v1', defaultInactivityMs = 15 * 60 * 1000;

  function getSessionId() {
    try {
      const now = Date.now(), threshold = (window.smartRecoConfig && window.smartRecoConfig.sessionInactivityMs) || defaultInactivityMs;
      let sid = sessionStorage.getItem(sessionKey);
      const lastAt = parseInt(sessionStorage.getItem(lastActivityKey) || '0', 10);
      if (!sid || (lastAt > 0 && (now - lastAt >= threshold))) {
        sid = eventId();
        sessionStorage.setItem(sessionKey, sid);
      }
      sessionStorage.setItem(lastActivityKey, now.toString());
      return sid;
    } catch (_) {
      return eventId();
    }
  }

  function add(event) {
    if (queue.length >= max || !event || !event.event_type) return;
    const currentSessionId = getSessionId();
    queue.push({ ...event, event_id: event.event_id || eventId(), session_id: event.session_id || currentSessionId, schema_version: event.schema_version || 1, page_path: event.page_path || location.pathname, occurred_at: event.occurred_at || new Date().toISOString() });
    try { window.dispatchEvent(new CustomEvent('smartreco:event_tracked', { detail: event })); } catch (_) {}
    if (queue.length >= batchSize) flush(false);
  }

  async function flush(beacon) {
    if (sending || !queue.length) return;
    const events = queue.splice(0, batchSize), body = JSON.stringify({ events });
    if (beacon && navigator.sendBeacon) {
      const ok = navigator.sendBeacon('/api/events/beacon', new Blob([body], { type: 'application/json' }));
      if (!ok) queue.unshift(...events);
      return;
    }
    sending = true;
    try {
      const response = await fetch('/api/events/batch', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() }, body, keepalive: true });
      if (!response.ok) queue.unshift(...events);
    } catch (_) { queue.unshift(...events); } finally { sending = false; }
  }

  function recentImpressions() {
    try {
      const now = Date.now(), saved = JSON.parse(sessionStorage.getItem(impressionKey) || '{}');
      Object.keys(saved).forEach(id => { if (now - saved[id] >= impressionTtl) delete saved[id]; });
      return saved;
    } catch (_) { return {}; }
  }

  function rememberImpression(id) {
    const saved = recentImpressions();
    saved[id] = Date.now();
    const entries = Object.entries(saved).sort((a, b) => b[1] - a[1]).slice(0, 100);
    try { sessionStorage.setItem(impressionKey, JSON.stringify(Object.fromEntries(entries))); } catch (_) { /* storage is optional */ }
  }

  function recentRelatedImpressions() {
    try {
      const now = Date.now(), saved = JSON.parse(sessionStorage.getItem(relatedImpressionKey) || '{}');
      Object.keys(saved).forEach(id => { if (now - saved[id] >= impressionTtl) delete saved[id]; });
      return saved;
    } catch (_) { return {}; }
  }

  function relatedImpression(card) {
    const id = card.dataset.courseId, dedupeKey = `${card.dataset.sourceCourseId}:${id}`;
    if (!id || qualifiedRelated.has(dedupeKey)) return;
    const saved = recentRelatedImpressions();
    if (saved[dedupeKey]) { qualifiedRelated.add(dedupeKey); return; }
    qualifiedRelated.add(dedupeKey); saved[dedupeKey] = Date.now();
    try { sessionStorage.setItem(relatedImpressionKey, JSON.stringify(Object.fromEntries(Object.entries(saved).sort((a, b) => b[1] - a[1]).slice(0, 100)))); } catch (_) { /* storage is optional */ }
    add({ event_type: 'COURSE_IMPRESSION', course_id: id, metadata: { source: 'related_course', source_course_id: card.dataset.sourceCourseId, target_course_id: id, rank: card.dataset.relatedRank } });
  }

  function qualifiedImpression(id) {
    if (qualified.has(id)) return;
    if (recentImpressions()[id]) { qualified.add(id); return; }
    qualified.add(id); rememberImpression(id); add({ event_type: 'COURSE_IMPRESSION', course_id: id });
  }

  function dwell() {
    if (sentDwell || document.visibilityState !== 'visible') return;
    const duration = Math.min(Math.max(Math.round(performance.now() - started), 1000), 1800000);
    if (duration >= 5000) {
      sentDwell = true;
      const courseId = document.querySelector('[data-course-view]')?.dataset.courseId || null;
      add({ event_type: 'DWELL', course_id: courseId, duration_ms: duration });
    }
  }

  window.smartRecoTracker = { track: add, flush };
  add({ event_type: 'PAGE_VIEW', metadata: { referrer: document.referrer || '' } });
  setInterval(() => flush(false), 5000);
  document.querySelectorAll('[data-course-view]').forEach(el => add({ event_type: 'COURSE_VIEW', course_id: el.dataset.courseId }));
  document.querySelectorAll('[data-course-click]').forEach(el => el.addEventListener('click', () => add({ event_type: 'COURSE_CLICK', course_id: el.closest('[data-course-id]')?.dataset.courseId, metadata: { source: location.pathname } })));
  document.querySelectorAll('[data-recommendation-click]').forEach(el => el.addEventListener('click', () => { const card = el.closest('[data-recommendation-item]'); add({ event_type: 'RECOMMENDATION_CLICK', course_id: el.dataset.courseId, metadata: { source: 'recommendation', recommendation_run_id: card?.dataset.recommendationRunId, recommendation_item_id: card?.dataset.recommendationItemId } }); }));
  document.querySelectorAll('[data-related-course-click]').forEach(el => el.addEventListener('click', () => { const card = el.closest('[data-related-course]'); add({ event_type: 'COURSE_CLICK', course_id: el.dataset.courseId, metadata: { source: 'related_course', source_course_id: card?.dataset.sourceCourseId, target_course_id: el.dataset.courseId, rank: card?.dataset.relatedRank } }); }));

  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      const id = entry.target.dataset.courseId;
      if (!id || qualified.has(id) || !entry.isIntersecting) { if (id && timers.has(id)) { clearTimeout(timers.get(id)); timers.delete(id); } return; }
      if (!timers.has(id)) timers.set(id, setTimeout(() => { timers.delete(id); qualifiedImpression(id); }, 1000));
    }), { threshold: .55 });
    document.querySelectorAll('.course-card[data-course-id]:not([data-recommendation-item]):not([data-related-course])').forEach(el => observer.observe(el));
    const recommendationObserver = new IntersectionObserver(entries => entries.forEach(entry => {
      const card = entry.target, itemId = card.dataset.recommendationItemId;
      if (!itemId || qualifiedRecommendations.has(itemId) || !entry.isIntersecting) { if (itemId && timers.has(`recommendation:${itemId}`)) { clearTimeout(timers.get(`recommendation:${itemId}`)); timers.delete(`recommendation:${itemId}`); } return; }
      const key = `recommendation:${itemId}`;
      if (!timers.has(key)) timers.set(key, setTimeout(() => { timers.delete(key); qualifiedRecommendations.add(itemId); add({ event_type: 'RECOMMENDATION_IMPRESSION', course_id: card.dataset.courseId, metadata: { source: 'recommendation', recommendation_run_id: card.dataset.recommendationRunId, recommendation_item_id: itemId, rank: card.dataset.recommendationRank } }); }, 1000));
    }), { threshold: .55 });
    document.querySelectorAll('[data-recommendation-item]').forEach(el => recommendationObserver.observe(el));
    const relatedObserver = new IntersectionObserver(entries => entries.forEach(entry => {
      const card = entry.target, id = card.dataset.courseId, key = `related:${card.dataset.sourceCourseId}:${id}`;
      if (!id || qualifiedRelated.has(`${card.dataset.sourceCourseId}:${id}`) || !entry.isIntersecting) { if (timers.has(key)) { clearTimeout(timers.get(key)); timers.delete(key); } return; }
      if (!timers.has(key)) timers.set(key, setTimeout(() => { timers.delete(key); relatedImpression(card); }, 1000));
    }), { threshold: .55 });
    document.querySelectorAll('[data-related-course]').forEach(el => relatedObserver.observe(el));
  }
  document.querySelectorAll('[data-filter-form]').forEach(form => form.addEventListener('submit', () => { const data = new FormData(form); add({ event_type: 'FILTER_CHANGE', metadata: { category: data.get('category'), difficulty: data.get('difficulty'), price: data.get('price'), sort: data.get('sort') } }); }));
  document.querySelectorAll('[data-search-form]').forEach(form => form.addEventListener('submit', () => { const query = (new FormData(form).get('q') || '').trim().replace(/\s+/g, ' '); if (query.length > 1) add({ event_type: 'SEARCH', search_query: query, metadata: { source: 'catalog' } }); }));
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') { dwell(); flush(true); } });
  window.addEventListener('pagehide', () => { dwell(); flush(true); });
})();
