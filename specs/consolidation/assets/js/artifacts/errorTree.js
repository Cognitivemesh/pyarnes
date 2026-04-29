import { el } from "../util.js";
import { refreshIcons } from "../boot.js";
import { copyButtons } from "../features/copyButtons.js";

// Error decision tree mounted into div[data-artifact="error-tree"].
//
// NOTE: scheduled for HTMX migration in step 8 — branch transitions
// will move to /api/artifact/error-tree.
export function errorTree(placeholder, data) {
  if (!Array.isArray(data) || data.length === 0) return;
  placeholder.replaceChildren();
  const wrap = el("div", { class: "decision-tree" });

  let chosen = null; // { kind, summary, snippet }
  const path = []; // ordered list of question states

  const buildSteps = () => {
    wrap.replaceChildren();
    let stepIndex = 0;
    let currentNode = data[0];
    while (currentNode) {
      const step = path[stepIndex];
      const block = el(
        "div",
        { class: "decision-tree-question" },
        el("i", { "data-lucide": "git-branch", "aria-hidden": "true" }),
        el("span", { class: "decision-tree-question-text" }, currentNode.question),
      );
      wrap.append(block);
      const choices = el(
        "div",
        { class: "decision-tree-choices" },
        el(
          "button",
          {
            type: "button",
            class: "decision-tree-choice" + (step?.answer === "yes" ? " is-active" : ""),
            onclick: () => {
              path[stepIndex] = { id: currentNode.id, answer: "yes" };
              path.length = stepIndex + 1;
              chosen = currentNode.yes_terminal ?? null;
              if (!chosen) {
                const next = data.find((n) => n.id === currentNode.no_next);
                if (next) chosen = null;
              }
              buildSteps();
            },
          },
          el("span", { class: "choice-label" }, "Yes"),
          el("span", null, currentNode.yes_terminal?.kind ?? "next question"),
        ),
        el(
          "button",
          {
            type: "button",
            class: "decision-tree-choice" + (step?.answer === "no" ? " is-active" : ""),
            onclick: () => {
              path[stepIndex] = { id: currentNode.id, answer: "no" };
              path.length = stepIndex + 1;
              if (currentNode.no_terminal) {
                chosen = currentNode.no_terminal;
              } else {
                chosen = null;
              }
              buildSteps();
            },
          },
          el("span", { class: "choice-label" }, "No"),
          el(
            "span",
            null,
            currentNode.no_terminal?.kind ??
              (currentNode.no_next ? "next question" : "—"),
          ),
        ),
      );
      wrap.append(choices);

      if (step?.answer === "yes" && currentNode.yes_terminal) break;
      if (step?.answer === "no" && currentNode.no_terminal) break;
      if (step?.answer === "no" && currentNode.no_next) {
        currentNode = data.find((n) => n.id === currentNode.no_next);
        stepIndex++;
        continue;
      }
      break;
    }
    if (chosen) {
      const term = el(
        "div",
        { class: "decision-tree-terminal" },
        el(
          "p",
          { class: "decision-tree-terminal-kind" },
          el("i", { "data-lucide": "flag", "aria-hidden": "true" }),
          chosen.kind,
        ),
        el("p", { class: "decision-tree-terminal-summary" }, chosen.summary),
        el("pre", null, el("code", null, chosen.snippet)),
      );
      wrap.append(term);
    }
    refreshIcons();
  };

  buildSteps();
  placeholder.append(wrap);
  copyButtons(placeholder);
  refreshIcons();
}
