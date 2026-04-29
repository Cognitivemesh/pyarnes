import { el } from "../util.js";
import { refreshIcons } from "../boot.js";

// Replace the markdown TOC extension's `¶` headerlink with a Lucide
// `link` icon and turn it into a click-to-copy. Toast feedback is
// dispatched via the global Alpine toast root (`show-toast` event).
export function headerCopyLinks(root) {
  const links = root.querySelectorAll(".markdown-body .headerlink");
  if (links.length === 0) return;
  for (const link of links) {
    link.replaceChildren(el("i", { "data-lucide": "link", "aria-hidden": "true" }));
    link.setAttribute("aria-label", "Copy link to section");
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      const href = link.getAttribute("href") || "";
      const url = window.location.origin + window.location.pathname + href;
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(url);
        } else {
          const ta = document.createElement("textarea");
          ta.value = url;
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.append(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
        }
        window.dispatchEvent(new CustomEvent("show-toast", { detail: "Link copied" }));
      } catch (err) {
        console.warn("specs.js: header-link copy failed:", err);
      }
    });
  }
  refreshIcons();
}
