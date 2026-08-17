(() => {
  const form = document.querySelector('[data-path-wizard]');
  if (!form) return;

  const steps = [...form.querySelectorAll('[data-step]')];
  const label = form.querySelector('[data-step-label]');
  const bar = form.querySelector('[data-progress-bar]');
  const domainOrder = [];
  let current = Math.max(0, Number(form.dataset.activeStep || 1) - 1);

  const inputs = group => [...group.querySelectorAll('input[type="checkbox"], input[type="radio"]')];
  const selected = group => inputs(group).filter(input => input.checked);
  const limitText = name => name.replaceAll('_', ' ');

  function setError(group, message = '') {
    const error = group.querySelector('[data-choice-error]');
    if (!error) return;
    error.textContent = message;
    error.hidden = !message;
    group.toggleAttribute('aria-invalid', Boolean(message));
  }

  function syncDomainOrder() {
    const checked = new Set(inputs(form.querySelector('[data-choice-key="selected_domains"]')).filter(input => input.checked).map(input => input.value));
    domainOrder.splice(0, domainOrder.length, ...domainOrder.filter(value => checked.has(value)), ...[...checked].filter(value => !domainOrder.includes(value)));
    const hidden = form.querySelector('[name="selected_domains_order"]');
    if (hidden) hidden.value = domainOrder.join(',');
  }

  function sync(group) {
    const values = selected(group);
    const max = Number(group.dataset.maxSelections || 0);
    const name = group.dataset.choiceKey || '';
    values.forEach((input, index) => {
      const number = input.closest('label')?.querySelector('[data-choice-number]');
      if (number) number.textContent = name === 'selected_domains' || name === 'goals' ? String(index + 1) : '';
      const role = input.closest('label')?.querySelector('[data-choice-role]');
      if (role && name === 'selected_domains') role.textContent = index === 0 ? 'Primary domain' : 'Secondary interest';
    });
    group.querySelectorAll('[data-choice-count]').forEach(counter => { counter.textContent = `${values.length} of ${max} selected`; });
    if (name === 'selected_domains') {
      syncDomainOrder();
      const summary = form.querySelector('[data-domain-summary]');
      if (summary) {
        summary.replaceChildren(...domainOrder.map((value, index) => {
          const item = document.createElement('li');
          const source = form.querySelector(`input[name="selected_domains"][value="${CSS.escape(value)}"]`);
          item.textContent = source?.closest('label')?.querySelector('strong')?.textContent || value;
          item.append(` — ${index === 0 ? 'Primary' : 'Secondary'}`);
          const action = document.createElement('button'); action.type = 'button'; action.className = 'link-button'; action.dataset.domainRemove = value; action.textContent = 'Remove';
          item.append(' ', action);
          if (index > 0) { const primary = document.createElement('button'); primary.type = 'button'; primary.className = 'link-button'; primary.dataset.domainPrimary = value; primary.textContent = 'Make primary'; item.append(' ', primary); }
          return item;
        }));
      }
    }
    if (max && values.length > max) setError(group, `You can choose up to ${max} ${limitText(name)}.`);
    updateNextButtons();
  }

  function validateGroup(group) {
    const min = Number(group.dataset.minSelections || 0);
    const count = selected(group).length;
    if (count < min) { setError(group, `Choose at least ${min} ${limitText(group.dataset.choiceKey || 'options')}.`); return false; }
    return true;
  }

  function validateStep() {
    let valid = true;
    steps[current].querySelectorAll('[data-choice-group]').forEach(group => { if (!validateGroup(group)) valid = false; });
    const required = [...steps[current].querySelectorAll('input[required], select[required], textarea[required]')];
    if (required.some(input => !input.value)) valid = false;
    if (!valid) (steps[current].querySelector('[aria-invalid="true"]') || required.find(input => !input.value))?.focus();
    return valid;
  }

  function updateNextButtons() {
    steps.forEach((step, index) => step.querySelectorAll('[data-next]').forEach(button => { button.disabled = index === current && step.querySelectorAll('[data-choice-group]').length > 0 && [...step.querySelectorAll('[data-choice-group]')].some(group => Number(group.dataset.minSelections || 0) > selected(group).length); }));
  }

  function show(index) {
    current = Math.max(0, Math.min(index, steps.length - 1));
    steps.forEach((step, i) => { step.hidden = i !== current; });
    label.textContent = `Step ${current + 1} of ${steps.length}`;
    bar.style.width = `${((current + 1) / steps.length) * 100}%`;
    updateNextButtons();
    if (current === steps.length - 1) renderReview();
  }

  function renderReview() {
    const target = form.querySelector('[data-review]'); if (!target) return;
    target.replaceChildren();
    const rows = [['Domains', 'selected_domains'], ['Learning goals', 'goals'], ['Current level', 'level'], ['Weekly time', 'weekly_hours'], ['Desired horizon', 'target_weeks'], ['Path size', 'path_length'], ['Budget', 'budget_type']];
    rows.forEach(([title, name]) => {
      const item = document.createElement('div'); item.className = 'review-item'; const strong = document.createElement('strong'); strong.textContent = title; const text = document.createElement('span');
      const checked = [...form.querySelectorAll(`[name="${name}"]:checked`)].map(input => input.closest('label')?.querySelector('strong')?.textContent || input.value);
      const value = form.elements[name]?.value || '';
      text.textContent = name === 'weekly_hours' ? `${value || '0'} hours/week` : name === 'target_weeks' ? ({'': 'Flexible', 1: '1 week', 4: '1 month', 8: '2 months', 12: '3 months'}[value] || 'Flexible') : name === 'path_length' ? ({FOCUSED: 'Focused path — 3–4 courses', BALANCED: 'Balanced path — 6–7 courses', EXTENDED: 'Deep path — 8 courses', DEEP: 'Deep path — 8 courses', AUTO: 'Let SmartReco decide — 3–8 courses'}[value] || 'Let SmartReco decide — 3–8 courses') : name === 'budget_type' ? ({FREE: 'Free courses only', UNDER_50: 'Under USD 50', UNDER_100: 'Under USD 100', UNDER_200: 'Under USD 200', FLEXIBLE: 'Flexible', CUSTOM: 'Custom maximum'}[value] || 'Flexible') : checked.join(', ') || 'Not selected'; item.append(strong, text); target.append(item);
    });
  }

  form.querySelectorAll('[data-choice-group]').forEach(group => {
    inputs(group).forEach(input => input.addEventListener('change', () => {
      const max = Number(group.dataset.maxSelections || 0);
      if (input.checked && max && selected(group).length > max) { input.checked = false; setError(group, `You can choose up to ${max} ${limitText(group.dataset.choiceKey || 'options')}. Remove one selection to choose another.`); input.focus(); return; }
      if (group.dataset.choiceKey === 'selected_domains') syncDomainOrder();
      setError(group); sync(group);
    }));
    sync(group);
  });
  form.addEventListener('click', event => {
    const primary = event.target.closest('[data-domain-primary]'); const remove = event.target.closest('[data-domain-remove]');
    if (primary) { domainOrder.splice(0, domainOrder.length, primary.dataset.domainPrimary, ...domainOrder.filter(value => value !== primary.dataset.domainPrimary)); sync(form.querySelector('[data-choice-key="selected_domains"]')); }
    if (remove) { const input = form.querySelector(`input[name="selected_domains"][value="${CSS.escape(remove.dataset.domainRemove)}"]`); if (input) input.checked = false; sync(form.querySelector('[data-choice-key="selected_domains"]')); }
  });

  function setButtonLoading(button) {
    if (!button) return;
    const rect = button.getBoundingClientRect();
    if (rect.width > 0) button.style.minWidth = `${rect.width}px`;
    if (rect.height > 0) button.style.minHeight = `${rect.height}px`;

    button.dataset.originalHtml = button.innerHTML;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.setAttribute('aria-label', 'Generating your path…');
    button.classList.add('path-generate-btn--loading');

    const spinner = document.createElement('span');
    spinner.className = 'path-generate-btn__spinner';
    spinner.setAttribute('aria-hidden', 'true');

    const text = document.createElement('span');
    text.className = 'path-generate-btn__text';
    text.textContent = 'Generating your path\u2026';

    button.replaceChildren(spinner, text);
  }

  function resetButtonLoading(button) {
    if (!button) return;
    button.disabled = false;
    button.removeAttribute('aria-busy');
    button.removeAttribute('aria-label');
    button.classList.remove('path-generate-btn--loading');
    button.style.minWidth = '';
    button.style.minHeight = '';
    if (button.dataset.originalHtml) {
      button.innerHTML = button.dataset.originalHtml;
      delete button.dataset.originalHtml;
    }
  }

  let isSubmitting = false;

  form.querySelectorAll('[data-next]').forEach(button => button.addEventListener('click', () => { if (validateStep()) show(current + 1); }));
  form.querySelectorAll('[data-back]').forEach(button => button.addEventListener('click', () => show(current - 1)));
  form.addEventListener('submit', (event) => {
    syncDomainOrder();
    if (!validateStep()) {
      event.preventDefault();
      return;
    }
    if (isSubmitting) {
      event.preventDefault();
      return;
    }

    const submitBtn = form.querySelector('[data-generate-roadmap-btn], button[type="submit"]');
    try {
      isSubmitting = true;
      form.setAttribute('aria-busy', 'true');
      setButtonLoading(submitBtn);
    } catch (err) {
      isSubmitting = false;
      form.removeAttribute('aria-busy');
      resetButtonLoading(submitBtn);
      throw err;
    }
  });

  window.addEventListener('pageshow', (event) => {
    if (event.persisted || isSubmitting) {
      isSubmitting = false;
      form.removeAttribute('aria-busy');
      const submitBtn = form.querySelector('[data-generate-roadmap-btn], button[type="submit"]');
      resetButtonLoading(submitBtn);
    }
  });

  form.querySelector('[data-domain-search]')?.addEventListener('input', event => { const needle = event.target.value.toLowerCase(); form.querySelectorAll('[data-domain-option]').forEach(option => { option.hidden = Boolean(needle && !option.innerText.toLowerCase().includes(needle)); }); });
  show(current);
})();
