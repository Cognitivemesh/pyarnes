import { el } from "../util.js";
import { refreshIcons } from "../boot.js";

// Adds a clipboard button to every `<pre>` in the rendered article. Idle
// state shows the clipboard icon; success state swaps to a check for 1.5s.
export function copyButtons(root) {
  const blocks = root.querySelectorAll(".markdown-body pre");
  for (const pre of blocks) {
    if (pre.querySelector(".copy-button")) continue;
    const button = el(
      "button",
      { type: "button", class: "copy-button", "aria-label": "Copy code" },
      el("i", { "data-lucide": "clipboard", "aria-hidden": "true" }),
      el("span", { class: "copy-label" }, "Copy"),
    );
    button.addEventListener("click", async () => {
      const code = pre.querySelector("code")?.innerText ?? pre.innerText;
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(code);
        } else {
          const ta = document.createElement("textarea");
          ta.value = code;
          ta.setAttribute("aria-hidden", "true");
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.append(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
        }
        button.classList.add("is-copied");
        button.querySelector(".copy-label").textContent = "Copied";
        const icon = button.querySelector("[data-lucide]");
        icon.setAttribute("data-lucide", "check");
        refreshIcons();
        setTimeout(() => {
          button.classList.remove("is-copied");
          button.querySelector(".copy-label").textContent = "Copy";
          const icon2 = button.querySelector("[data-lucide]");
          if (icon2) icon2.setAttribute("data-lucide", "clipboard");
          refreshIcons();
        }, 1500);
      } catch (err) {
        console.warn("specs.js: copy failed:", err);
      }
    });
    pre.append(button);
  }
}
