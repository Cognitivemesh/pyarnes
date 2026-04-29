import { el, trapFocus, sessionCache } from "../util.js";
import { refreshIcons } from "../boot.js";

// Centered overlay search palette. Searches across spec titles, section
// headings, and diagrams. Section index is built lazily on first open.
//
// NOTE: scheduled for HTMX migration in step 6 — search will move to
// /api/palette and this module will shrink to overlay open/close.
export function commandPalette(root, index) {
  if (!index?.pages) return;
  const trigger = root.querySelector("[data-specs-action='open-palette']");
  if (!trigger) return;
  trigger.removeAttribute("hidden");

  const tabs = ["All", "Specs", "Sections", "Diagrams"];
  let activeTab = "All";
  let activeResult = 0;
  let cachedSections = sessionCache.get("palette.sections", null);

  const overlay = el(
    "div",
    { class: "cmdk-overlay", role: "dialog", "aria-modal": "true", "aria-label": "Find anything" },
    el(
      "div",
      { class: "cmdk-panel" },
      el("input", {
        type: "text",
        class: "cmdk-input",
        placeholder: "Search specs, sections, diagrams…",
        autocomplete: "off",
        spellcheck: "false",
      }),
      el(
        "div",
        { class: "cmdk-tablist", role: "tablist" },
        el(
          "div",
          { class: "tab-strip" },
          ...tabs.map((t) =>
            el(
              "button",
              {
                type: "button",
                class: "tab-button" + (t === "All" ? " is-active" : ""),
                "data-tab": t,
              },
              t,
            ),
          ),
        ),
      ),
      el("ul", { class: "cmdk-results", role: "listbox" }),
    ),
  );
  document.body.append(overlay);

  const input = overlay.querySelector(".cmdk-input");
  const results = overlay.querySelector(".cmdk-results");
  let releaseFocus = null;

  const fetchSections = async () => {
    if (cachedSections) return cachedSections;
    const sections = [];
    for (const page of index.pages) {
      if (page.group !== "Consolidation" && page.slug !== "readme") continue;
      try {
        const res = await fetch(page.href, { headers: { Accept: "text/html" } });
        if (!res.ok) continue;
        const html = await res.text();
        const doc = new DOMParser().parseFromString(html, "text/html");
        for (const h of doc.querySelectorAll(".markdown-body h2, .markdown-body h3")) {
          const id = h.id;
          if (!id) continue;
          sections.push({
            slug: page.slug,
            page: page.title,
            heading: h.textContent.replace(/¶|🔗|↩/g, "").trim(),
            href: `${page.href}#${id}`,
            level: h.tagName === "H2" ? 2 : 3,
          });
        }
      } catch {
        /* network blip — skip this page */
      }
    }
    cachedSections = sections;
    sessionCache.set("palette.sections", sections);
    return sections;
  };

  const score = (text, query) => {
    if (!query) return 1;
    text = text.toLowerCase();
    if (text.includes(query)) return 2;
    let qi = 0;
    for (const ch of text) {
      if (ch === query[qi]) qi++;
      if (qi === query.length) return 1;
    }
    return 0;
  };

  const renderResults = async () => {
    const query = input.value.trim().toLowerCase();
    const items = [];
    if (activeTab === "All" || activeTab === "Specs") {
      for (const page of index.pages) {
        if (page.group === "Diagrams") continue;
        const s = score(page.title, query);
        if (s > 0) items.push({ kind: "spec", title: page.title, meta: page.group, href: page.href, score: s });
      }
    }
    if (activeTab === "All" || activeTab === "Diagrams") {
      for (const page of index.pages) {
        if (page.group !== "Diagrams") continue;
        const s = score(page.title, query);
        if (s > 0) items.push({ kind: "diagram", title: page.title, meta: "Diagram", href: page.href, score: s });
      }
    }
    if (activeTab === "All" || activeTab === "Sections") {
      const sections = await fetchSections();
      for (const sec of sections) {
        const s = score(`${sec.page} ${sec.heading}`, query);
        if (s > 0) items.push({ kind: "section", title: sec.heading, meta: sec.page, href: sec.href, score: s });
      }
    }
    items.sort((a, b) => b.score - a.score || a.title.localeCompare(b.title));
    const limited = items.slice(0, 80);
    results.replaceChildren();
    if (limited.length === 0) {
      results.append(el("li", { class: "cmdk-empty" }, "No matches"));
      activeResult = 0;
      return;
    }
    limited.forEach((item, i) => {
      const iconName = item.kind === "diagram" ? "workflow" : item.kind === "section" ? "hash" : "file-text";
      const li = el(
        "li",
        null,
        el(
          "button",
          {
            type: "button",
            class: "cmdk-result" + (i === activeResult ? " is-active" : ""),
            "data-href": item.href,
            "data-index": i,
          },
          el("i", { "data-lucide": iconName, "aria-hidden": "true" }),
          el("span", null, item.title),
          el("span", { class: "cmdk-result-meta" }, item.meta),
        ),
      );
      results.append(li);
    });
    refreshIcons();
  };

  const open = () => {
    overlay.classList.add("is-open");
    input.value = "";
    activeResult = 0;
    renderResults();
    setTimeout(() => input.focus(), 0);
    releaseFocus = trapFocus(overlay);
  };

  const close = () => {
    overlay.classList.remove("is-open");
    releaseFocus?.();
    releaseFocus = null;
    trigger.focus();
  };

  trigger.addEventListener("click", open);

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && overlay.classList.contains("is-open")) {
      close();
    }
  });

  input.addEventListener("input", () => {
    activeResult = 0;
    renderResults();
  });

  input.addEventListener("keydown", (event) => {
    const buttons = results.querySelectorAll(".cmdk-result");
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (buttons.length === 0) return;
      activeResult = (activeResult + 1) % buttons.length;
      buttons.forEach((b, i) => b.classList.toggle("is-active", i === activeResult));
      buttons[activeResult]?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (buttons.length === 0) return;
      activeResult = (activeResult - 1 + buttons.length) % buttons.length;
      buttons.forEach((b, i) => b.classList.toggle("is-active", i === activeResult));
      buttons[activeResult]?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter") {
      event.preventDefault();
      const target = buttons[activeResult];
      if (target) window.location.href = target.dataset.href;
    }
  });

  results.addEventListener("click", (event) => {
    const button = event.target.closest(".cmdk-result");
    if (!button) return;
    window.location.href = button.dataset.href;
  });

  overlay.querySelectorAll(".tab-button").forEach((b) => {
    b.addEventListener("click", () => {
      activeTab = b.dataset.tab;
      activeResult = 0;
      overlay.querySelectorAll(".tab-button").forEach((x) => x.classList.toggle("is-active", x === b));
      renderResults();
    });
  });
}
