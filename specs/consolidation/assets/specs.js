// specs.js — entry point. Each feature is its own ES module under js/.
// Failures are isolated by a try/catch wrapper so one feature can't poison
// the rest of the page.

import { readDataIsland, refreshIcons, refreshHighlighting } from "./js/boot.js";
import { progressRail } from "./js/features/progressRail.js";
import { smoothAnchors } from "./js/features/smoothAnchors.js";
import { copyButtons } from "./js/features/copyButtons.js";
import { scrollspy } from "./js/features/scrollspy.js";
import { sidebarChromeCollapse } from "./js/features/sidebarChromeCollapse.js";
import { sidebarCollapse } from "./js/features/sidebarCollapse.js";
import { sidebarFilters } from "./js/features/sidebarFilters.js";
import { specPager } from "./js/features/specPager.js";
import { commandPalette } from "./js/features/commandPalette.js";
import { depGraphDrawer } from "./js/features/depGraphDrawer.js";
import { filterableTable } from "./js/features/filterableTable.js";
import { headerCopyLinks } from "./js/features/headerCopyLinks.js";
import { decorateAdmonitions } from "./js/features/decorateAdmonitions.js";
import { topbarBreadcrumb } from "./js/features/topbarBreadcrumb.js";
import { registerSpecPreviewDirective } from "./js/features/specPreview.js";
import { mountArtifacts } from "./js/artifacts/index.js";

// Register the Alpine directive eagerly so it's available before Alpine
// scans the DOM. specPreview.js handles the case where Alpine itself
// hasn't loaded yet.
registerSpecPreviewDirective();

function init() {
  const index = readDataIsland();
  const root = document;
  const features = [
    () => progressRail(root),
    () => smoothAnchors(root),
    () => copyButtons(root),
    () => scrollspy(root),
    () => sidebarChromeCollapse(root),
    () => sidebarCollapse(root),
    () => sidebarFilters(root),
    () => specPager(root, index),
    () => commandPalette(root, index),
    () => depGraphDrawer(root, index),
    () => filterableTable(root),
    () => headerCopyLinks(root),
    () => decorateAdmonitions(root),
    () => topbarBreadcrumb(root),
    () => mountArtifacts(root, index),
  ];
  for (const f of features) {
    try {
      f();
    } catch (err) {
      console.warn("specs.js feature failed:", err);
    }
  }
  refreshIcons();
  refreshHighlighting(root);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
