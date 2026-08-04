(function () {
  const cards = document.querySelectorAll("[data-feedback-card]");
  const manualBtn = document.querySelector("[data-manual-generate-btn]");
  if (!cards.length && !manualBtn) return;

  const tracker = window.smartRecoTracker;
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const liveRegion = document.createElement("div");
  liveRegion.className = "sr-only";
  liveRegion.setAttribute("role", "status");
  liveRegion.setAttribute("aria-live", "polite");
  document.body.append(liveRegion);

  const announce = (message) => { liveRegion.textContent = message; };
  const actionValue = (action, key) => action?.[key] || action?.[key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase())];

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

  function setPendingState(card, message, refresh) {
    const overlay = card.querySelector("[data-feedback-overlay]");
    if (!overlay) return;
    overlay.hidden = false;
    overlay.innerHTML = "";
    const status = document.createElement("div");
    status.className = "feedback-replacement-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const heading = document.createElement("h4");
    heading.textContent = refresh ? "Feedback saved" : "Finding a better match";
    const text = document.createElement("p");
    text.textContent = message;
    status.append(heading, text);
    if (!refresh) {
      const spinner = document.createElement("div");
      spinner.className = "loading-indicator";
      spinner.setAttribute("aria-hidden", "true");
      status.prepend(spinner);
    } else {
      const link = document.createElement("a");
      link.className = "button secondary";
      link.href = "/recommendations";
      link.textContent = "Refresh suggestions";
      status.append(link);
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
    setPendingState(card, "We’re combining your feedback with your overall learning activity. Refresh this page shortly if a new course does not appear automatically.", true);
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
      card.classList.add("is-feedback-pending");
      setPendingState(card, "We’re combining your feedback with your overall learning activity.", false);
      try {
        const response = await fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin", headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("feedback_failed");
        const payload = await response.json();
        await pollReplacement(card, payload.recommendation_run_id || runId, rejectedItemId, visibleCourseIds);
      } catch (_) {
        setPendingState(card, "Your feedback could not be saved. Refresh later to try again.", true);
      }
    });
    card.addEventListener("keydown", (event) => { if (event.key === "Escape" && !overlay.hidden) closeOverlay(card, true); });
  }

  cards.forEach(wireCard);

  document.querySelectorAll("[data-replacement-pending]").forEach((pendingCard) => {
    const visibleCourseIds = new Set([...document.querySelectorAll("[data-recommendation-item]")].map((item) => item.dataset.courseId));
    pollReplacement(pendingCard, null, null, visibleCourseIds);
  });

  if (manualBtn) {
    manualBtn.addEventListener("click", async () => {
      manualBtn.disabled = true;
      const originalText = manualBtn.textContent;
      manualBtn.textContent = "Generating recommendations...";
      const container = document.querySelector("[data-manual-generate-container]");
      if (container) {
        let status = container.querySelector("[data-generate-status]");
        if (!status) {
          status = document.createElement("p");
          status.dataset.generateStatus = "true";
          status.className = "recommendation-generate-status";
          status.setAttribute("role", "status");
          status.setAttribute("aria-live", "polite");
          status.style.marginTop = "1rem";
          status.style.fontWeight = "500";
          container.append(status);
        }
        status.textContent = "We are preparing your personalized recommendations. Please wait...";
      }
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
              const slots = rec?.recommendation_slots || rec?.recommendations || [];
              const activeSlots = slots.filter((slot) => slot.state === "ACTIVE" || slot.course || slot.item);
              if (activeSlots.length > 0 || pollingAttempts >= 20) {
                clearInterval(pollInterval);
                window.location.reload();
              }
            } else if (pollingAttempts >= 20) {
              clearInterval(pollInterval);
              window.location.reload();
            }
          } catch (_) {
            if (pollingAttempts >= 20) {
              clearInterval(pollInterval);
              window.location.reload();
            }
          }
        }, 1500);
      } catch (_) {
        manualBtn.disabled = false;
        manualBtn.textContent = originalText;
        announce("Unable to generate recommendations right now. Please try again.");
      }
    });
  }
})();
