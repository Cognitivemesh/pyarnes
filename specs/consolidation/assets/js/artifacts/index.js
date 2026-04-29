import { refreshIcons, refreshHighlighting } from "../boot.js";
import { errorTree } from "./errorTree.js";
import { lifecycleFsm } from "./lifecycleFsm.js";
import { hookWiring } from "./hookWiring.js";

// Walk every div.artifact[data-artifact] placeholder and mount the matching
// widget. Called once at boot from the orchestrator.
export function mountArtifacts(root, index) {
  if (!index?.artifacts) return;
  const placeholders = root.querySelectorAll("div.artifact[data-artifact]");
  for (const ph of placeholders) {
    const kind = ph.dataset.artifact;
    const data = index.artifacts[kind];
    if (!data) continue;
    if (kind === "error-tree") errorTree(ph, data);
    else if (kind === "lifecycle-fsm") lifecycleFsm(ph, data);
    else if (kind === "hook-wiring") hookWiring(ph, data);
  }
  refreshIcons();
  refreshHighlighting(root);
}
