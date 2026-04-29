import { rafThrottle } from "../util.js";

export function progressRail(root) {
  const rail = root.querySelector(".progress-rail");
  if (!rail) return;
  const update = rafThrottle(() => {
    const doc = document.documentElement;
    const max = doc.scrollHeight - doc.clientHeight;
    const pct = max > 0 ? Math.min(1, Math.max(0, doc.scrollTop / max)) : 0;
    rail.style.transform = `scaleX(${pct})`;
  });
  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update, { passive: true });
  update();
}
