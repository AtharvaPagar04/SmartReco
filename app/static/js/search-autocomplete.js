(function () {
  'use strict';

  const localKey = 'smartreco_recent_searches_v1';
  const debounceMs = 250;
  const maxRecent = 6;
  const anonymous = document.body.dataset.authenticated !== 'true';

  function normalize(value) {
    return String(value || '').trim().replace(/\s+/g, ' ').slice(0, 200);
  }

  function readLocal() {
    try {
      const value = JSON.parse(localStorage.getItem(localKey) || '[]');
      return Array.isArray(value) ? value.filter(item => item && typeof item.query === 'string' && item.query.trim()) : [];
    } catch (_) { return []; }
  }

  function saveLocal(query) {
    const clean = normalize(query);
    if (clean.length < 2) return;
    const normalized = clean.toLowerCase();
    const recent = readLocal().filter(item => item.normalized !== normalized);
    recent.unshift({ query: clean, normalized, searched_at: Date.now() });
    try { localStorage.setItem(localKey, JSON.stringify(recent.slice(0, maxRecent))); } catch (_) { /* optional browser storage */ }
  }

  function setup(root) {
    const input = root.querySelector('input[role="combobox"]');
    const list = root.querySelector('[role="listbox"]');
    const status = root.querySelector('[data-search-status]');
    const form = root.closest('form');
    if (!input || !list || !form) return;
    let timer = null, controller = null, requestNumber = 0, active = -1, items = [];

    function close() {
      list.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      active = -1;
    }

    function open() {
      if (!items.length) return close();
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }

    function render(title, nextItems) {
      items = nextItems;
      active = -1;
      list.replaceChildren();
      if (!items.length) return close();
      const heading = document.createElement('div');
      heading.className = 'search-group-title';
      heading.setAttribute('role', 'presentation');
      heading.textContent = title;
      list.appendChild(heading);
      items.forEach((item, index) => {
        const option = document.createElement('div');
        option.id = `${input.id}-option-${index}`;
        option.className = 'search-option';
        option.setAttribute('role', 'option');
        option.setAttribute('aria-selected', 'false');
        option.dataset.index = String(index);
        const label = document.createElement('span');
        label.className = 'search-option-label';
        label.textContent = item.label || item.query || item.value;
        const meta = document.createElement('small');
        meta.textContent = item.type === 'recent' ? 'Recent search' : `${item.type[0].toUpperCase()}${item.type.slice(1)}${item.category ? ` · ${item.category}` : ''}`;
        option.append(label, meta);
        option.addEventListener('pointerdown', event => { event.preventDefault(); select(index); });
        list.appendChild(option);
      });
      status.textContent = `${items.length} ${title.toLowerCase()} available.`;
      open();
    }

    function highlight(index) {
      if (!items.length) return;
      active = (index + items.length) % items.length;
      list.querySelectorAll('[role="option"]').forEach((option, optionIndex) => {
        const selected = optionIndex === active;
        option.setAttribute('aria-selected', String(selected));
        option.classList.toggle('active', selected);
      });
      input.setAttribute('aria-activedescendant', `${input.id}-option-${active}`);
    }

    function select(index) {
      const item = items[index];
      if (!item) return;
      input.value = normalize(item.value || item.query || item.label);
      if (anonymous) saveLocal(input.value);
      close();
      if (form.requestSubmit) form.requestSubmit(); else form.submit();
    }

    async function showRecent() {
      if (!anonymous) {
        try {
          const response = await fetch('/api/search/recent', { headers: { Accept: 'application/json' } });
          if (!response.ok) return close();
          const data = await response.json();
          if (normalize(input.value)) return;
          return render('Recent searches', (data.recent_searches || []).map(item => ({ type: 'recent', label: item.query, value: item.query })));
        } catch (_) { return close(); }
      }
      render('Recent searches', readLocal().slice(0, maxRecent).map(item => ({ type: 'recent', label: item.query, value: item.query })));
    }

    function fetchSuggestions(query) {
      if (controller) controller.abort();
      const sequence = ++requestNumber;
      controller = new AbortController();
      fetch(`/api/search/suggestions?q=${encodeURIComponent(query)}&limit=8`, { signal: controller.signal, headers: { Accept: 'application/json' } })
        .then(response => response.ok ? response.json() : Promise.reject(new Error('suggestions unavailable')))
        .then(data => { if (sequence === requestNumber && normalize(input.value).toLowerCase() === query.toLowerCase()) render('Suggestions', data.suggestions || []); })
        .catch(error => { if (error.name !== 'AbortError') close(); });
    }

    input.addEventListener('focus', () => {
      const query = normalize(input.value);
      if (!query) showRecent();
      else if (query.length >= 2) fetchSuggestions(query);
    });
    input.addEventListener('input', () => {
      const query = normalize(input.value);
      if (timer) clearTimeout(timer);
      if (controller) controller.abort();
      if (!query) return showRecent();
      close();
      if (query.length < 2) return;
      timer = setTimeout(() => fetchSuggestions(query), debounceMs);
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' && !list.hidden) { event.preventDefault(); highlight(active + 1); }
      else if (event.key === 'ArrowUp' && !list.hidden) { event.preventDefault(); highlight(active - 1); }
      else if (event.key === 'Enter' && active >= 0 && !list.hidden) { event.preventDefault(); select(active); }
      else if (event.key === 'Escape') close();
      else if (event.key === 'Tab') close();
    });
    form.addEventListener('submit', () => {
      const query = normalize(input.value);
      input.value = query;
      if (anonymous) saveLocal(query);
      close();
    });
  }

  document.querySelectorAll('[data-search-autocomplete]').forEach(setup);
  document.addEventListener('pointerdown', event => {
    document.querySelectorAll('[data-search-autocomplete]').forEach(root => { if (!root.contains(event.target)) { const input = root.querySelector('input[role="combobox"]'); if (input) { input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); } const list = root.querySelector('[role="listbox"]'); if (list) list.hidden = true; } });
  });
})();
