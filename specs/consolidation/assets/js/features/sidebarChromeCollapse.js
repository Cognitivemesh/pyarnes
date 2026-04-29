import { el, storage } from "../util.js";

// Adds a chevron toggle next to the brand title. Click collapses the
// sidebar-chrome description copy. State persisted in localStorage.
//
// NOTE: scheduled for replacement by Alpine `x-data="{ open: $persist(true) }"`
// in the template once Alpine is wired up. This file is the modular extraction
// of the previously-inlined logic.
export function sidebarChromeCollapse(root) {
  const chrome = root.querySelector(".sidebar-chrome");
  if (!chrome) return;
  const brand = chrome.querySelector(".brand");
  if (!brand) return;
  if (chrome.querySelector(".chrome-toggle")) return;

  const toggle = el(
    "button",
    {
      type: "button",
      class: "chrome-toggle",
      "aria-label": "Toggle viewer description",
    },
    el("i", { "data-lucide": "chevron-down", "aria-hidden": "true" }),
  );
  brand.append(toggle);

  if (storage.get("chrome.collapsed", false)) {
    chrome.classList.add("is-collapsed");
  }
  toggle.addEventListener("click", () => {
    const collapsed = chrome.classList.toggle("is-collapsed");
    storage.set("chrome.collapsed", collapsed);
  });
}
