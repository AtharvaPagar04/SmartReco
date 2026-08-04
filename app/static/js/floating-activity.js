(function () {
  'use strict';

  function initFloatingActivityWidget() {
    if (document.getElementById('floating-activity-widget')) return;

    // Create widget container
    const widget = document.createElement('div');
    widget.id = 'floating-activity-widget';
    widget.className = 'floating-activity-widget';
    widget.setAttribute('role', 'region');
    widget.setAttribute('aria-label', 'Real-time Recently Viewed Courses');

    widget.innerHTML = `
      <div class="activity-drag-handle" id="activity-drag-handle">
        <div class="activity-header-title">
          <span class="live-pulse-dot" title="Live activity monitoring active"></span>
          <strong class="handle-text">Recently viewed courses</strong>
        </div>
        <div class="activity-header-actions">
          <button type="button" class="activity-action-btn" id="activity-minimize-btn" title="Minimize / Expand" aria-label="Minimize">—</button>
          <button type="button" class="activity-action-btn" id="activity-close-btn" title="Hide floating widget" aria-label="Close">✕</button>
        </div>
      </div>
      <div class="activity-widget-body" id="activity-widget-body">
        <div class="activity-widget-list" id="activity-widget-list">
          <p class="activity-empty-text">Loading live activity...</p>
        </div>
      </div>
      <div class="activity-resize-handle" id="activity-resize-handle" title="Drag to resize"></div>
    `;

    const launcher = document.createElement('button');
    launcher.type = 'button';
    launcher.id = 'floating-activity-launcher';
    launcher.className = 'floating-activity-launcher';
    launcher.title = 'Open Recently Viewed Courses';
    launcher.innerHTML = `<span class="live-pulse-dot"></span> Activity Feed`;
    launcher.style.display = 'none';

    document.body.appendChild(widget);
    document.body.appendChild(launcher);

    const dragHandle = document.getElementById('activity-drag-handle');
    const minimizeBtn = document.getElementById('activity-minimize-btn');
    const closeBtn = document.getElementById('activity-close-btn');
    const widgetBody = document.getElementById('activity-widget-body');
    const listContainer = document.getElementById('activity-widget-list');
    const resizeHandle = document.getElementById('activity-resize-handle');

    // State persistence keys
    const POS_KEY = 'smartreco_activity_pos';
    const SIZE_KEY = 'smartreco_activity_size';
    const STATE_KEY = 'smartreco_activity_state'; // 'expanded', 'minimized', 'closed'

    // Load saved position
    const savedPos = localStorage.getItem(POS_KEY);
    if (savedPos) {
      try {
        const { left, top } = JSON.parse(savedPos);
        const maxLeft = Math.max(10, window.innerWidth - 300);
        const maxTop = Math.max(10, window.innerHeight - 150);
        widget.style.left = `${Math.max(10, Math.min(left, maxLeft))}px`;
        widget.style.top = `${Math.max(10, Math.min(top, maxTop))}px`;
        widget.style.right = 'auto';
        widget.style.bottom = 'auto';
      } catch (e) {}
    } else {
      // Default position bottom right
      widget.style.right = '24px';
      widget.style.bottom = '24px';
    }

    // Load saved size
    const savedSize = localStorage.getItem(SIZE_KEY);
    if (savedSize) {
      try {
        const { width, height } = JSON.parse(savedSize);
        if (width >= 280) widget.style.width = `${width}px`;
        if (height >= 160) widget.style.height = `${height}px`;
      } catch (e) {}
    }

    // Load saved minimized / closed state
    const savedState = localStorage.getItem(STATE_KEY);
    if (savedState === 'minimized') {
      widget.classList.add('is-minimized');
      minimizeBtn.textContent = '□';
      minimizeBtn.title = 'Expand';
    } else if (savedState === 'closed') {
      widget.style.display = 'none';
      launcher.style.display = 'inline-flex';
    }

    // 1. DRAGGING LOGIC
    let isDragging = false;
    let startX = 0, startY = 0;
    let initialLeft = 0, initialTop = 0;

    function onDragStart(e) {
      if (e.target.closest('.activity-action-btn')) return;
      isDragging = true;
      const clientX = e.type === 'touchstart' ? e.touches[0].clientX : e.clientX;
      const clientY = e.type === 'touchstart' ? e.touches[0].clientY : e.clientY;

      const rect = widget.getBoundingClientRect();
      initialLeft = rect.left;
      initialTop = rect.top;
      startX = clientX;
      startY = clientY;

      widget.style.right = 'auto';
      widget.style.bottom = 'auto';
      widget.style.left = `${initialLeft}px`;
      widget.style.top = `${initialTop}px`;
      widget.classList.add('is-dragging');

      document.addEventListener('mousemove', onDragMove);
      document.addEventListener('mouseup', onDragEnd);
      document.addEventListener('touchmove', onDragMove, { passive: false });
      document.addEventListener('touchend', onDragEnd);
    }

    function onDragMove(e) {
      if (!isDragging) return;
      if (e.type === 'touchmove') e.preventDefault();
      const clientX = e.type === 'touchmove' ? e.touches[0].clientX : e.clientX;
      const clientY = e.type === 'touchmove' ? e.touches[0].clientY : e.clientY;

      const deltaX = clientX - startX;
      const deltaY = clientY - startY;

      let newLeft = initialLeft + deltaX;
      let newTop = initialTop + deltaY;

      const maxLeft = window.innerWidth - widget.offsetWidth;
      const maxTop = window.innerHeight - widget.offsetHeight;

      newLeft = Math.max(10, Math.min(newLeft, maxLeft - 10));
      newTop = Math.max(10, Math.min(newTop, maxTop - 10));

      widget.style.left = `${newLeft}px`;
      widget.style.top = `${newTop}px`;
    }

    function onDragEnd() {
      if (!isDragging) return;
      isDragging = false;
      widget.classList.remove('is-dragging');

      document.removeEventListener('mousemove', onDragMove);
      document.removeEventListener('mouseup', onDragEnd);
      document.removeEventListener('touchmove', onDragMove);
      document.removeEventListener('touchend', onDragEnd);

      const rect = widget.getBoundingClientRect();
      localStorage.setItem(POS_KEY, JSON.stringify({ left: Math.round(rect.left), top: Math.round(rect.top) }));
    }

    dragHandle.addEventListener('mousedown', onDragStart);
    dragHandle.addEventListener('touchstart', onDragStart, { passive: false });

    // 2. RESIZING LOGIC
    let isResizing = false;
    let startWidth = 0, startHeight = 0;

    function onResizeStart(e) {
      e.preventDefault();
      e.stopPropagation();
      isResizing = true;
      const clientX = e.type === 'touchstart' ? e.touches[0].clientX : e.clientX;
      const clientY = e.type === 'touchstart' ? e.touches[0].clientY : e.clientY;

      startWidth = widget.offsetWidth;
      startHeight = widget.offsetHeight;
      startX = clientX;
      startY = clientY;

      widget.classList.add('is-resizing');

      document.addEventListener('mousemove', onResizeMove);
      document.addEventListener('mouseup', onResizeEnd);
      document.addEventListener('touchmove', onResizeMove, { passive: false });
      document.addEventListener('touchend', onResizeEnd);
    }

    function onResizeMove(e) {
      if (!isResizing) return;
      if (e.type === 'touchmove') e.preventDefault();
      const clientX = e.type === 'touchmove' ? e.touches[0].clientX : e.clientX;
      const clientY = e.type === 'touchmove' ? e.touches[0].clientY : e.clientY;

      const newWidth = Math.max(280, Math.min(650, startWidth + (clientX - startX)));
      const newHeight = Math.max(160, Math.min(600, startHeight + (clientY - startY)));

      widget.style.width = `${newWidth}px`;
      widget.style.height = `${newHeight}px`;
    }

    function onResizeEnd() {
      if (!isResizing) return;
      isResizing = false;
      widget.classList.remove('is-resizing');

      document.removeEventListener('mousemove', onResizeMove);
      document.removeEventListener('mouseup', onResizeEnd);
      document.removeEventListener('touchmove', onResizeMove);
      document.removeEventListener('touchend', onResizeEnd);

      localStorage.setItem(SIZE_KEY, JSON.stringify({ width: widget.offsetWidth, height: widget.offsetHeight }));
    }

    resizeHandle.addEventListener('mousedown', onResizeStart);
    resizeHandle.addEventListener('touchstart', onResizeStart, { passive: false });

    // 3. MINIMIZE / CLOSE LOGIC
    minimizeBtn.addEventListener('click', () => {
      const isMin = widget.classList.toggle('is-minimized');
      minimizeBtn.textContent = isMin ? '□' : '—';
      minimizeBtn.title = isMin ? 'Expand' : 'Minimize';
      localStorage.setItem(STATE_KEY, isMin ? 'minimized' : 'expanded');
    });

    closeBtn.addEventListener('click', () => {
      widget.style.display = 'none';
      launcher.style.display = 'inline-flex';
      localStorage.setItem(STATE_KEY, 'closed');
    });

    launcher.addEventListener('click', () => {
      launcher.style.display = 'none';
      widget.style.display = 'flex';
      localStorage.setItem(STATE_KEY, widget.classList.contains('is-minimized') ? 'minimized' : 'expanded');
    });

    // 4. REAL-TIME DATA FETCHING & RENDERING
    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    async function fetchLiveActivity() {
      try {
        const response = await fetch('/api/events/recent', { credentials: 'same-origin' });
        if (!response.ok) return;
        const data = await response.json();
        const items = data.recently_viewed || [];

        if (items.length === 0) {
          listContainer.innerHTML = '<p class="activity-empty-text">Your recently viewed courses will update live here as you browse.</p>';
          return;
        }

        const rowsHtml = items.map(item => `
          <div class="activity-row">
            <div class="activity-row-main">
              <a href="/courses/${escapeHtml(item.slug)}" class="activity-course-title">${escapeHtml(item.title)}</a>
              <span class="activity-course-meta">
                ${escapeHtml(item.category)}${item.dwell_minutes ? ` · ${item.dwell_minutes} min focused` : ''}
              </span>
            </div>
            <time class="activity-course-time">${escapeHtml(item.last_viewed_at || '')}</time>
          </div>
        `).join('');

        listContainer.innerHTML = rowsHtml;
      } catch (err) {
        console.warn('Failed to refresh floating activity:', err);
      }
    }

    // Initial fetch
    fetchLiveActivity();

    // Poll every 3 seconds for real-time live updates
    setInterval(fetchLiveActivity, 3000);

    // Listen to local tracker event dispatch for instant update on click/view
    window.addEventListener('smartreco:event_tracked', fetchLiveActivity);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFloatingActivityWidget);
  } else {
    initFloatingActivityWidget();
  }
})();
