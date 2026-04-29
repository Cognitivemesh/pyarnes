import { el, storage } from "../util.js";

// Per-group collapse toggle in the sidebar nav. State persisted as a Set
// of heading texts in localStorage.
//
// NOTE: scheduled for replacement by Alpine in the template.
export function sidebarCollapse(root) {
  const groups = root.querySelectorAll(".sidebar-nav .nav-group");
  const collapsed = new Set(storage.get("sidebar.collapsed", []) || []);
  for (const group of groups) {
    const heading = group.querySelector(".nav-heading");
    if (!heading) continue;
    const headingText = heading.textContent.trim();
    const toggle = el(
      "button",
      { type: "button", class: "collapse-toggle", "aria-label": `Toggle ${headingText}` },
      el("i", { "data-lucide": "chevron-right", "aria-hidden": "true" }),
    );
    heading.prepend(toggle);
    const isCollapsed = collapsed.has(headingText);
    if (isCollapsed) group.classList.add("is-collapsed");
    else toggle.classList.add("is-expanded");

    toggle.addEventListener("click", () => {
      group.classList.toggle("is-collapsed");
      const nowCollapsed = group.classList.contains("is-collapsed");
      toggle.classList.toggle("is-expanded", !nowCollapsed);
      if (nowCollapsed) collapsed.add(headingText);
      else collapsed.delete(headingText);
      storage.set("sidebar.collapsed", [...collapsed]);
    });
  }
}
