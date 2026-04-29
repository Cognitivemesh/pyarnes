import { el } from "../util.js";
import { refreshIcons } from "../boot.js";

// Section breadcrumb in the topbar. Watches the article's H2/H3 headings
// via IntersectionObserver and dispatches a `current-heading-changed`
// event with the current chain. The topbar's path-label is replaced
// with a chain of `<a>` crumbs whenever the chain has at least one entry.
export function topbarBreadcrumb(root) {
  const topbar = root.querySelector(".topbar");
  if (!topbar) return;
  const article = root.querySelector(".markdown-body");
  if (!article) return;
  const eyebrow = topbar.querySelector(".eyebrow");
  const pathLabel = topbar.querySelector(".path-label");
  if (!eyebrow || !pathLabel) return;
  const headings = [...article.querySelectorAll("h2, h3")].filter((h) => h.id);
  if (headings.length === 0) return;

  const breadcrumb = el("nav", { class: "topbar-breadcrumb", hidden: "" });
  pathLabel.parentNode.insertBefore(breadcrumb, pathLabel.nextSibling);

  const originalEyebrow = eyebrow.textContent;
  const pageTitle = (root.querySelector(".markdown-body h1")?.textContent ?? "").replace(/¶|🔗/g, "").trim();

  const setChain = (chain) => {
    if (!chain || chain.length === 0) {
      breadcrumb.hidden = true;
      pathLabel.hidden = false;
      eyebrow.textContent = originalEyebrow;
      return;
    }
    pathLabel.hidden = true;
    breadcrumb.hidden = false;
    eyebrow.textContent = "Section";
    const parts = [];
    if (pageTitle) {
      parts.push(el("span", { class: "crumb-page" }, pageTitle));
    }
    chain.forEach((h, i) => {
      if (i > 0 || pageTitle) parts.push(el("span", { class: "crumb-sep", "aria-hidden": "true" }, "›"));
      parts.push(
        el(
          "a",
          { class: "crumb", href: `#${h.id}` },
          h.textContent.replace(/¶|🔗/g, "").trim(),
        ),
      );
    });
    breadcrumb.replaceChildren(...parts);
  };

  let activeH2 = null;
  let activeH3 = null;
  const computeChain = () => {
    const chain = [];
    if (activeH2) chain.push(activeH2);
    if (activeH3 && activeH3.compareDocumentPosition(activeH2 ?? activeH3) & Node.DOCUMENT_POSITION_PRECEDING) {
      chain.push(activeH3);
    } else if (activeH3 && !activeH2) {
      chain.push(activeH3);
    }
    setChain(chain);
  };

  const observer = new IntersectionObserver(
    (entries) => {
      let changed = false;
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const tag = entry.target.tagName;
        if (tag === "H2") {
          activeH2 = entry.target;
          activeH3 = null;
          changed = true;
        } else if (tag === "H3") {
          activeH3 = entry.target;
          changed = true;
        }
      }
      if (changed) computeChain();
    },
    { rootMargin: "-96px 0px -65% 0px", threshold: [0, 1] },
  );
  for (const heading of headings) observer.observe(heading);
}
