import { sessionCache } from "../util.js";

// Hover preview popover for any `<a class="spec-ref" x-spec-preview="<slug>">`.
// Lazy-fetches the target page once; caches the parsed H1 + first paragraph
// in sessionStorage so subsequent hovers are instant.
//
// Registered as an Alpine directive at boot time. If Alpine isn't loaded
// yet, retry on next tick.
const POPOVER_CLASS = "spec-preview-popover";
let activePopover = null;

async function fetchPreview(slug) {
  const cacheKey = `preview.${slug}`;
  const cached = sessionCache.get(cacheKey, null);
  if (cached) return cached;
  const href = `/specs/consolidation/${slug}.md`;
  try {
    const res = await fetch(href, { headers: { Accept: "text/html" } });
    if (!res.ok) return null;
    const html = await res.text();
    const doc = new DOMParser().parseFromString(html, "text/html");
    const h1 = doc.querySelector(".markdown-body h1");
    const firstPara = doc.querySelector(".markdown-body > p, .markdown-body > .spec-meta + p");
    const title = h1 ? h1.textContent.replace(/¶|🔗/g, "").trim() : slug;
    const summary = firstPara ? firstPara.textContent.trim().slice(0, 280) : "";
    const data = { title, summary, href };
    sessionCache.set(cacheKey, data);
    return data;
  } catch {
    return null;
  }
}

function dismiss() {
  if (activePopover) {
    activePopover.remove();
    activePopover = null;
  }
}

function showPopover(target, data) {
  dismiss();
  if (!data) return;
  const popover = document.createElement("aside");
  popover.className = POPOVER_CLASS;
  const title = document.createElement("h3");
  title.textContent = data.title;
  const summary = document.createElement("p");
  summary.textContent = data.summary || "(no summary available)";
  const link = document.createElement("a");
  link.className = "spec-preview-link";
  link.href = data.href;
  link.textContent = "Read full →";
  popover.append(title, summary, link);
  document.body.append(popover);

  const rect = target.getBoundingClientRect();
  const top = window.scrollY + rect.bottom + 6;
  let left = window.scrollX + rect.left;
  const popoverRect = popover.getBoundingClientRect();
  if (left + popoverRect.width > window.innerWidth - 12) {
    left = window.innerWidth - popoverRect.width - 12;
  }
  popover.style.top = `${top}px`;
  popover.style.left = `${Math.max(12, left)}px`;
  activePopover = popover;
}

export function registerSpecPreviewDirective() {
  const tryRegister = () => {
    if (typeof window.Alpine === "undefined") {
      // Alpine may load slightly after specs.js. Retry on next frame.
      requestAnimationFrame(tryRegister);
      return;
    }
    window.Alpine.directive("spec-preview", (el, { expression }, { cleanup }) => {
      const slug = expression || el.getAttribute("data-spec-preview-slug") || "";
      if (!slug) return;
      let pending = false;
      const onEnter = async () => {
        if (pending) return;
        pending = true;
        const data = await fetchPreview(slug);
        pending = false;
        if (document.activeElement === el || el.matches(":hover")) {
          showPopover(el, data);
        }
      };
      el.addEventListener("mouseenter", onEnter);
      el.addEventListener("focus", onEnter);
      el.addEventListener("mouseleave", dismiss);
      el.addEventListener("blur", dismiss);
      cleanup(() => {
        el.removeEventListener("mouseenter", onEnter);
        el.removeEventListener("focus", onEnter);
        el.removeEventListener("mouseleave", dismiss);
        el.removeEventListener("blur", dismiss);
      });
    });
  };
  tryRegister();
}
