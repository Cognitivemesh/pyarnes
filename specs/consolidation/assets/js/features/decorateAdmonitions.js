import { el } from "../util.js";
import { refreshIcons } from "../boot.js";

// Prepend a Lucide icon to every admonition title, keyed by the admonition's
// type class (`note`, `warning`, etc.). Pure DOM walk — pairs with the
// per-type CSS rules in specs.css.
const ADMONITION_ICONS = {
  note: "info",
  warning: "alert-triangle",
  caution: "alert-triangle",
  tip: "lightbulb",
  hint: "lightbulb",
  success: "check-circle",
  danger: "zap",
  important: "alert-octagon",
  question: "help-circle",
  example: "code",
};

export function decorateAdmonitions(root) {
  const admonitions = root.querySelectorAll(".markdown-body .admonition");
  if (admonitions.length === 0) return;
  for (const node of admonitions) {
    const title = node.querySelector(".admonition-title");
    if (!title || title.querySelector("[data-lucide]")) continue;
    const type = [...node.classList].find((c) => c !== "admonition") || "note";
    const icon = ADMONITION_ICONS[type] || "info";
    title.prepend(el("i", { "data-lucide": icon, "aria-hidden": "true" }));
  }
  refreshIcons();
}
