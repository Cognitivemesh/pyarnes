import { el } from "../util.js";

// Hook-wiring artifact mounted into div[data-artifact="hook-wiring"].
// Three-column rows that expand to show their handler location.
//
// NOTE: scheduled for HTMX migration in step 8.
export function hookWiring(placeholder, data) {
  if (!Array.isArray(data) || data.length === 0) return;
  placeholder.replaceChildren();
  const wrap = el("div", { class: "hook-wiring" });
  for (const row of data) {
    const r = el(
      "div",
      { class: "hook-row", role: "button", tabindex: "0" },
      el("span", { class: "hook-row-event" }, row.event),
      el("span", { class: "hook-row-handler" }, row.handler),
      el("span", { class: "hook-row-artifact" }, row.artifact),
    );
    const detail = el("div", { class: "hook-detail" }, row.location);
    const toggle = () => {
      const expanded = r.classList.toggle("is-expanded");
      detail.style.display = expanded ? "block" : "none";
    };
    r.addEventListener("click", toggle);
    r.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggle();
      }
    });
    wrap.append(r, detail);
  }
  placeholder.append(wrap);
}
