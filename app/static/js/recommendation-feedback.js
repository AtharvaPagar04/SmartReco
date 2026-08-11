(function () {
  const cards = document.querySelectorAll("[data-feedback-card]");
  const manualBtn = document.querySelector("[data-manual-generate-btn]");
  const pendingCards = document.querySelectorAll("[data-replacement-pending]");
  if (!cards.length && !manualBtn && !pendingCards.length) return;

  const tracker = window.smartRecoTracker;
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const liveRegion = document.createElement("div");
  liveRegion.className = "sr-only";
  liveRegion.setAttribute("role", "status");
  liveRegion.setAttribute("aria-live", "polite");
  document.body.append(liveRegion);

  const announce = (message) => { liveRegion.textContent = message; };
  const actionValue = (action, key) => action?.[key] || action?.[key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase())];

  let isRefreshing = false;

  async function requestRecommendationRefresh(triggerBtn) {
    if (isRefreshing) return;
    isRefreshing = true;

    const allButtons = document.querySelectorAll("[data-manual-generate-btn]");
    allButtons.forEach((btn) => {
      btn.disabled = true;
    });

    const primaryText = triggerBtn ? triggerBtn.textContent : "";
    if (triggerBtn) {
      triggerBtn.textContent = "Generating recommendations...";
    }

    const container = document.querySelector("[data-manual-generate-container]");
    let statusEl = null;
    if (container) {
      statusEl = container.querySelector("[data-generate-status]");
      if (!statusEl) {
        statusEl = document.createElement("p");
        statusEl.dataset.generateStatus = "true";
        statusEl.className = "recommendation-generate-status";
        statusEl.setAttribute("role", "status");
        statusEl.setAttribute("aria-live", "polite");
        statusEl.style.marginTop = "1rem";
        statusEl.style.fontWeight = "500";
        container.append(statusEl);
      }
      statusEl.textContent = "We are preparing your personalized recommendations. Please wait...";
    } else if (triggerBtn) {
      const parentBlock = triggerBtn.closest(".feedback-replacement-status") || triggerBtn.closest("[data-feedback-card], [data-recommendation-card], .recommendation-card");
      if (parentBlock) {
        statusEl = parentBlock.querySelector("[data-generate-status]");
        if (!statusEl) {
          statusEl = document.createElement("p");
          statusEl.dataset.generateStatus = "true";
          statusEl.className = "recommendation-generate-status";
          statusEl.setAttribute("role", "status");
          statusEl.setAttribute("aria-live", "polite");
          statusEl.style.marginTop = "0.75rem";
          statusEl.style.fontWeight = "500";
          parentBlock.append(statusEl);
        }
        statusEl.textContent = "Preparing recommendations. Please wait...";
      }
    }

    announce("We are preparing your personalized recommendations. Please wait...");

    let previousRunId = null;
    try {
      const initRes = await fetch("/api/recommendations/current", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (initRes.ok) {
        const initPayload = await initRes.json();
        previousRunId = initPayload.recommendation?.run_id || null;
      }
    } catch (_) {}

    try {
      const response = await fetch("/api/recommendations/refresh", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
        },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("refresh_failed");

      let pollingAttempts = 0;
      const pollInterval = setInterval(async () => {
        pollingAttempts += 1;
        try {
          const currRes = await fetch("/api/recommendations/current", {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
          });
          if (currRes.ok) {
            const payload = await currRes.json();
            const rec = payload.recommendation;
            const newRunId = rec?.run_id;
            const slots = rec?.recommendation_slots || rec?.recommendations || rec?.items || [];
            const activeSlots = slots.filter((slot) => {
              const item = slot.item || (slot.course ? slot : null);
              return (slot.state === "ACTIVE" || !slot.state) && item && item.course;
            });
            const isNewRun = !previousRunId || (newRunId && newRunId !== previousRunId);
            if (isNewRun && activeSlots.length > 0) {
              clearInterval(pollInterval);
              window.location.reload();
              return;
            }
          }
        } catch (_) {}

        if (pollingAttempts >= 25) {
          clearInterval(pollInterval);
          isRefreshing = false;
          allButtons.forEach((btn) => {
            btn.disabled = false;
          });
          if (triggerBtn) {
            triggerBtn.textContent = primaryText || "Refresh suggestions";
          }
          if (statusEl) {
            statusEl.textContent = "Unable to complete refresh right now. Please try again.";
          }
          announce("Unable to complete refresh right now. Please try again.");
        }
      }, 1500);
    } catch (_) {
      isRefreshing = false;
      allButtons.forEach((btn) => {
        btn.disabled = false;
      });
      if (triggerBtn) {
        triggerBtn.textContent = primaryText || "Refresh suggestions";
      }
      if (statusEl) {
        statusEl.textContent = "Unable to complete refresh right now. Please try again.";
      }
      announce("Unable to complete refresh right now. Please try again.");
    }
  }

  document.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-manual-generate-btn]");
    if (btn) {
      event.preventDefault();
      requestRecommendationRefresh(btn);
    }
  });

  function actionControl(label, url, method, secondary) {
    if (!label || !url) return null;
    const className = `button${secondary ? " secondary" : ""}`;
    if (method === "POST") {
      const form = document.createElement("form");
      form.method = "post";
      form.action = url;
      const token = document.createElement("input");
      token.type = "hidden";
      token.name = "csrf_token";
      token.value = csrf;
      const button = document.createElement("button");
      button.type = "submit";
      button.className = className;
      button.textContent = label;
      form.append(token, button);
      return form;
    }
    const link = document.createElement("a");
    link.className = className;
    link.href = url;
    link.textContent = label;
    return link;
  }

  function renderActions(card, action) {
    const stack = card.querySelector(".course-action-stack");
    if (!stack) return;
    stack.replaceChildren();
    const primary = actionControl(actionValue(action, "primary_label"), actionValue(action, "primary_url"), actionValue(action, "primary_method"), false);
    const secondary = actionControl(actionValue(action, "secondary_label"), actionValue(action, "secondary_url"), actionValue(action, "secondary_method"), true);
    if (primary) stack.append(primary);
    if (secondary) stack.append(secondary);
  }

  function setPendingState(card, message, stateType) {
    const overlay = card.querySelector("[data-feedback-overlay]");
    if (!overlay) return;
    overlay.hidden = false;
    overlay.innerHTML = "";
    card.classList.add("is-feedback-pending");

    const status = document.createElement("div");
    status.className = "feedback-replacement-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");

    const heading = document.createElement("h4");
    if (stateType === "success") {
      heading.textContent = "Feedback saved";
    } else if (stateType === "error") {
      heading.textContent = "Unable to save feedback";
    } else {
      heading.textContent = "Finding a better match";
    }

    const text = document.createElement("p");
    text.textContent = message;
    status.append(heading, text);

    if (stateType === "pending" || !stateType) {
      const spinner = document.createElement("div");
      spinner.className = "loading-indicator";
      spinner.setAttribute("aria-hidden", "true");
      status.prepend(spinner);
    } else if (stateType === "success") {
      const button = document.createElement("button");
      button.className = "button secondary";
      button.type = "button";
      button.dataset.manualGenerateBtn = "true";
      button.textContent = "Refresh suggestions";
      status.append(button);
    } else if (stateType === "error") {
      const button = document.createElement("button");
      button.className = "button secondary";
      button.type = "button";
      button.textContent = "Try again";
      button.addEventListener("click", () => window.location.reload());
      status.append(button);
    }
    overlay.append(status);
  }

  function closeOverlay(card, reset) {
    const overlay = card.querySelector("[data-feedback-overlay]");
    const trigger = card.querySelector("[data-feedback-open]");
    if (!overlay) return;
    if (reset) card.querySelector("[data-feedback-form]")?.reset();
    overlay.hidden = true;
    trigger?.setAttribute("aria-expanded", "false");
    card.classList.remove("is-feedback-open", "is-feedback-pending");
    trigger?.focus();
  }

  function replacementCard(template, item, runId) {
    const card = template.cloneNode(true);
    const course = item.course;
    card.dataset.recommendationRunId = runId;
    card.dataset.recommendationItemId = item.item_id;
    card.dataset.recommendationRank = item.rank;
    card.dataset.courseId = course.id;
    card.querySelector(".course-category").textContent = course.category;
    const titleLink = card.querySelector(".recommendation-card__header h3 a");
    titleLink.href = `/courses/${course.slug}`;
    titleLink.textContent = course.title;
    titleLink.dataset.courseId = course.id;
    card.querySelector(".skill-connection").textContent = item.skill_connection || "Next practical skill";
    card.querySelector(".recommendation-explanation p").textContent = item.reason;
    card.querySelector(".recommendation-benefit p").textContent = item.how_it_helps;
    const evidence = card.querySelector(".recommendation-evidence__chips");
    if (evidence) {
      evidence.replaceChildren();
      (item.evidence_labels || []).forEach((label) => { const chip = document.createElement("span"); chip.className = "evidence-chip"; chip.textContent = label; evidence.append(chip); });
      card.querySelector(".recommendation-evidence").hidden = !(item.evidence_labels || []).length;
    }
    const meta = card.querySelector(".course-meta");
    meta.textContent = `${String(course.difficulty).replace(/^./, (value) => value.toUpperCase()).toLowerCase()} · ${Number(course.price) === 0 ? "Free" : `${course.currency} ${course.price}`}`;
    renderActions(card, item.action);
    const overlay = card.querySelector("[data-feedback-overlay]");
    overlay.hidden = true;
    overlay.id = `feedback-overlay-${item.item_id}`;
    overlay.setAttribute("aria-labelledby", `feedback-title-${item.item_id}`);
    overlay.setAttribute("aria-describedby", `feedback-description-${item.item_id}`);
    overlay.querySelector("h4").id = `feedback-title-${item.item_id}`;
    overlay.querySelector(".feedback-overlay__description").id = `feedback-description-${item.item_id}`;
    const form = overlay.querySelector("[data-feedback-form]");
    form.action = `/api/recommendations/items/${item.item_id}/feedback`;
    const trigger = card.querySelector("[data-feedback-open]");
    trigger?.setAttribute("aria-controls", overlay.id);
    trigger?.setAttribute("aria-expanded", "false");
    form.querySelectorAll("input[type=radio]").forEach((input) => { input.checked = false; });
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    return card;
  }

  async function pollReplacement(card, runId, rejectedItemId, visibleCourseIds) {
    if (card.dataset.polling === "true") return;
    card.dataset.polling = "true";
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      if (document.visibilityState === "hidden") continue;
      const response = await fetch("/api/recommendations/current", { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!response.ok) continue;
      const payload = await response.json();
      const recommendation = payload.recommendation;
      const candidates = recommendation?.recommendation_slots || recommendation?.recommendations || recommendation?.items || [];
      const replacement = candidates.find((slot) => {
        const item = slot.item || (slot.course ? slot : null);
        return item && item.course && (slot.state === "ACTIVE" || !slot.state) && !visibleCourseIds.has(item.course.id) && item.course.id !== rejectedItemId;
      });
      if (replacement) {
        const replacementItem = replacement.item || replacement;
        const next = replacementCard(card, replacementItem, recommendation.run_id);
        card.replaceWith(next);
        wireCard(next);
        tracker?.track?.({ event_type: "RECOMMENDATION_REPLACEMENT_SHOWN", course_id: replacementItem.course.id, metadata: { recommendation_run_id: recommendation.run_id, recommendation_item_id: replacementItem.item_id } });
        announce("A new recommendation is available.");
        return;
      }
    }
    card.dataset.polling = "false";
    setPendingState(card, "We’re combining your feedback with your overall learning activity. Refresh suggestions if a new course does not appear automatically.", "success");
    announce("Your feedback was saved, but a replacement is taking longer than expected.");
  }

  function wireCard(card) {
    const overlay = card.querySelector("[data-feedback-overlay]");
    const trigger = card.querySelector("[data-feedback-open]");
    const form = card.querySelector("[data-feedback-form]");
    const submit = form?.querySelector("[type=submit]");
    if (!overlay || !trigger || !form) return;
    overlay.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    trigger.addEventListener("click", () => {
      overlay.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      card.classList.add("is-feedback-open");
      tracker?.track?.({ event_type: "RECOMMENDATION_FEEDBACK_OPENED", course_id: card.dataset.courseId, metadata: { recommendation_item_id: card.dataset.recommendationItemId } });
      overlay.querySelector("input[type=radio]")?.focus();
    });
    overlay.querySelectorAll("[data-feedback-cancel]").forEach((button) => button.addEventListener("click", () => closeOverlay(card, true)));
    form.querySelectorAll("input[type=radio]").forEach((input) => input.addEventListener("change", () => { submit.disabled = false; }));
    form.addEventListener("submit", async (event) => {
      if (!window.fetch) return;
      event.preventDefault();
      const visibleCourseIds = new Set([...document.querySelectorAll("[data-recommendation-item]")].map((item) => item.dataset.courseId));
      const runId = card.dataset.recommendationRunId;
      const rejectedItemId = card.dataset.recommendationItemId;
      submit.disabled = true;
      setPendingState(card, "We’re combining your feedback with your overall learning activity.", "pending");
      try {
        const response = await fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin", headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("feedback_failed");
        const payload = await response.json();
        announce("Feedback saved. Finding a better match.");
        await pollReplacement(card, payload.recommendation_run_id || runId, rejectedItemId, visibleCourseIds);
      } catch (_) {
        setPendingState(card, "Your feedback could not be saved. Please try again.", "error");
        announce("Your feedback could not be saved.");
      }
    });
    card.addEventListener("keydown", (event) => { if (event.key === "Escape" && !overlay.hidden) closeOverlay(card, true); });
  }

  cards.forEach(wireCard);

  pendingCards.forEach((pendingCard) => {
    const visibleCourseIds = new Set([...document.querySelectorAll("[data-recommendation-item]")].map((item) => item.dataset.courseId));
    pollReplacement(pendingCard, null, null, visibleCourseIds);
  });
})();
