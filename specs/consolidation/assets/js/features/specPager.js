import { el } from "../util.js";

// Prev/next pager rendered at the bottom of consolidation specs. Order
// follows index.pages (which the server sorts via consolidation_nav_order).
export function specPager(root, index) {
  if (!index?.pages) return;
  const article = root.querySelector(".markdown-body");
  if (!article) return;
  const specs = index.pages.filter((p) => p.group === "Consolidation");
  if (specs.length === 0) return;
  const current = index.current;
  const idx = specs.findIndex((p) => p.slug === current);
  if (idx < 0) return; // overview / diagrams pages get no pager

  const prev = idx > 0 ? specs[idx - 1] : null;
  const next = idx < specs.length - 1 ? specs[idx + 1] : null;
  if (!prev && !next) return;

  const pagerLink = (page, direction) =>
    page
      ? el(
          "a",
          { href: page.href, class: direction === "next" ? "spec-pager-next" : "" },
          el(
            "span",
            { class: "spec-pager-direction" },
            el("i", { "data-lucide": direction === "next" ? "arrow-right" : "arrow-left", "aria-hidden": "true" }),
            direction === "next" ? "Next" : "Previous",
          ),
          el("span", { class: "spec-pager-title" }, page.title),
        )
      : el("span", { class: "spec-pager-empty" }, "");

  const pager = el(
    "nav",
    { class: "spec-pager", "aria-label": "Spec navigation" },
    pagerLink(prev, "prev"),
    pagerLink(next, "next"),
  );
  article.append(pager);
}
