// Boot helpers — the data island, icon refresh, and Prism rehighlight logic
// that more than one feature needs. No external imports; safe to import from
// any module.

const DATA_ISLAND_ID = "__specs_index__";

export function readDataIsland() {
  // The server emits the JSON with `</` defanged so it cannot break the
  // surrounding <script> tag. Reverse the defang on parse.
  const node = document.getElementById(DATA_ISLAND_ID);
  if (!node) {
    console.warn("specs.js: data island missing — palette and dep-graph disabled");
    return null;
  }
  try {
    return JSON.parse(node.textContent.replace(/<\\\//g, "</"));
  } catch (err) {
    console.warn("specs.js: data island parse failed:", err);
    return null;
  }
}

export function refreshIcons() {
  if (typeof window.lucide !== "undefined") {
    try {
      window.lucide.createIcons();
    } catch (err) {
      console.warn("specs.js: lucide refresh failed:", err);
    }
  }
}

// Line-numbers threshold: short snippets read better without the gutter.
const PRISM_LINE_NUMBERS_THRESHOLD = 4;

function applyLineNumbers(root) {
  // Mark every multi-line `<pre>` inside the rendered article so the
  // line-numbers plugin renders a gutter. Short snippets (< threshold)
  // stay clean.
  const blocks = root.querySelectorAll(".markdown-body pre, .artifact pre");
  for (const pre of blocks) {
    if (pre.classList.contains("line-numbers")) continue;
    const code = pre.querySelector("code");
    if (!code) continue;
    const lines = code.textContent.replace(/\n+$/, "").split("\n").length;
    if (lines >= PRISM_LINE_NUMBERS_THRESHOLD) {
      pre.classList.add("line-numbers");
    }
  }
}

export function refreshHighlighting(root = document) {
  // Prism auto-runs once on DOMContentLoaded. Call this manually after
  // injecting fresh code (artifact mounts, decision-tree snippets, etc.)
  // so newly-added blocks pick up tokens + line numbers.
  applyLineNumbers(root);
  if (typeof window.Prism !== "undefined") {
    try {
      window.Prism.highlightAllUnder(root);
    } catch (err) {
      console.warn("specs.js: prism refresh failed:", err);
    }
  }
}
