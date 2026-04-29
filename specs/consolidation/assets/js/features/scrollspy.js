// Scrollspy on the right TOC. Highlights the heading currently in view.
export function scrollspy(root) {
  const tocLinks = root.querySelectorAll(".toc-panel .toc a[href^='#']");
  if (tocLinks.length === 0) return;
  const linkById = new Map();
  for (const link of tocLinks) {
    const id = decodeURIComponent(link.getAttribute("href").slice(1));
    linkById.set(id, link);
  }
  const headings = [...linkById.keys()]
    .map((id) => document.getElementById(id))
    .filter(Boolean);
  if (headings.length === 0) return;

  let current = null;
  const setActive = (id) => {
    if (current === id) return;
    if (current) linkById.get(current)?.classList.remove("is-active");
    current = id;
    if (id) linkById.get(id)?.classList.add("is-active");
  };

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (visible) setActive(visible.target.id);
    },
    { rootMargin: "-96px 0px -65% 0px", threshold: [0, 1] },
  );
  for (const heading of headings) observer.observe(heading);
}
