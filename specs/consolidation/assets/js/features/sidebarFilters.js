import { el, storage } from "../util.js";

// Filter chips above the sidebar nav: All / Specs / Diagrams. Click to
// hide groups whose heading doesn't match. Persisted in localStorage.
//
// NOTE: scheduled for replacement by Alpine in the template.
export function sidebarFilters(root) {
  const nav = root.querySelector(".sidebar-nav");
  if (!nav) return;
  const groups = [...nav.querySelectorAll(".nav-group")];
  if (groups.length === 0) return;
  const groupNames = groups.map((g) => g.querySelector(".nav-heading")?.textContent?.trim() ?? "");
  const choices = ["All", ...groupNames.filter(Boolean)];

  const chips = el("ul", { class: "sidebar-filter-chips" });
  const filter = el(
    "div",
    { class: "sidebar-filter" },
    el("i", { "data-lucide": "filter", "aria-hidden": "true" }),
    el("span", null, "Filter"),
    chips,
  );

  let active = storage.get("sidebar.filter", "All");
  if (!choices.includes(active)) active = "All";

  const apply = () => {
    for (const group of groups) {
      const name = group.querySelector(".nav-heading")?.textContent?.trim();
      const visible = active === "All" || name === active;
      group.classList.toggle("is-hidden", !visible);
    }
    for (const chip of chips.querySelectorAll(".tab-button")) {
      chip.classList.toggle("is-active", chip.textContent.trim() === active);
    }
  };

  for (const choice of choices) {
    const chip = el(
      "li",
      null,
      el(
        "button",
        {
          type: "button",
          class: "tab-button",
          onclick: () => {
            active = choice;
            storage.set("sidebar.filter", active);
            apply();
          },
        },
        choice,
      ),
    );
    chips.append(chip);
  }
  nav.prepend(filter);
  apply();
}
