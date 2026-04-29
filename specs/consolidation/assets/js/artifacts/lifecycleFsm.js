import { el } from "../util.js";

// Lifecycle FSM artifact mounted into div[data-artifact="lifecycle-fsm"].
// Six states arranged in two columns; click a state to see transitions.
//
// NOTE: scheduled for HTMX migration in step 8.
export function lifecycleFsm(placeholder, data) {
  if (!data?.states || !data?.transitions) return;
  placeholder.replaceChildren();
  const wrap = el("div", { class: "fsm-explorer" });
  const detail = el("div", { class: "fsm-detail" });

  // Layout: arrange states in two columns. Active states left, terminal right.
  const columns = {
    initial: { x: 80, slots: [] },
    active: { x: 80, slots: [] },
    terminal: { x: 280, slots: [] },
  };
  for (const state of data.states) {
    const bucket = state.kind in columns ? state.kind : "active";
    columns[bucket].slots.push(state);
  }
  const leftStack = [...columns.initial.slots, ...columns.active.slots];
  const positions = new Map();
  const stepY = 80;
  leftStack.forEach((s, i) => {
    positions.set(s.id, { x: 80, y: 60 + i * stepY, w: 120, h: 40 });
  });
  columns.terminal.slots.forEach((s, i) => {
    positions.set(s.id, { x: 280, y: 60 + i * stepY, w: 120, h: 40 });
  });
  const totalH = Math.max(leftStack.length, columns.terminal.slots.length) * stepY + 80;

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("class", "fsm-canvas");
  svg.setAttribute("viewBox", `0 0 460 ${totalH}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Lifecycle finite state machine");

  const edgeEls = [];
  for (const t of data.transitions) {
    const a = positions.get(t.from);
    const b = positions.get(t.to);
    if (!a || !b) continue;
    const x1 = a.x + a.w;
    const y1 = a.y + a.h / 2;
    const x2 = b.x;
    const y2 = b.y + b.h / 2;
    const line = document.createElementNS(svgNS, "path");
    const dx = (x2 - x1) / 2;
    line.setAttribute("class", "fsm-edge");
    line.setAttribute("d", `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`);
    line.dataset.from = t.from;
    line.dataset.to = t.to;
    svg.append(line);
    edgeEls.push(line);
  }

  const nodeEls = new Map();
  for (const s of data.states) {
    const p = positions.get(s.id);
    if (!p) continue;
    const g = document.createElementNS(svgNS, "g");
    g.setAttribute("class", `fsm-node${s.kind === "terminal" ? " is-terminal" : ""}`);
    g.dataset.id = s.id;
    g.setAttribute("tabindex", "0");
    const rect = document.createElementNS(svgNS, "rect");
    rect.setAttribute("x", p.x);
    rect.setAttribute("y", p.y);
    rect.setAttribute("width", p.w);
    rect.setAttribute("height", p.h);
    const label = document.createElementNS(svgNS, "text");
    label.setAttribute("x", p.x + p.w / 2);
    label.setAttribute("y", p.y + p.h / 2);
    label.textContent = s.label;
    g.append(rect, label);
    g.addEventListener("click", () => activate(s.id));
    g.addEventListener("focus", () => activate(s.id));
    svg.append(g);
    nodeEls.set(s.id, g);
  }

  const activate = (id) => {
    const state = data.states.find((s) => s.id === id);
    if (!state) return;
    for (const [nid, g] of nodeEls) g.classList.toggle("is-active", nid === id);
    for (const e of edgeEls) {
      e.classList.toggle("is-active", e.dataset.from === id || e.dataset.to === id);
    }
    const inbound = data.transitions.filter((t) => t.to === id);
    const outbound = data.transitions.filter((t) => t.from === id);
    detail.replaceChildren(
      el("p", { class: "fsm-detail-label" }, "State"),
      el("p", { class: "fsm-detail-name" }, state.label),
      el("p", { class: "fsm-detail-section" }, state.summary),
      el("p", { class: "fsm-detail-label" }, "Enters via"),
      inbound.length === 0
        ? el("p", { class: "fsm-detail-section" }, "—")
        : el(
            "ul",
            { class: "fsm-detail-list" },
            ...inbound.map((t) => el("li", null, `${t.trigger}  ←  ${t.from}`)),
          ),
      el("p", { class: "fsm-detail-label" }, "Exits via"),
      outbound.length === 0
        ? el("p", { class: "fsm-detail-section" }, "Terminal — no outgoing transitions.")
        : el(
            "ul",
            { class: "fsm-detail-list" },
            ...outbound.map((t) => el("li", null, `${t.trigger}  →  ${t.to}`)),
          ),
      data.guarantees && state.kind === "terminal"
        ? el(
            "ul",
            { class: "fsm-guarantees" },
            ...data.guarantees.map((g) => el("li", null, g)),
          )
        : null,
    );
  };

  wrap.append(svg, detail);
  placeholder.append(wrap);
  activate(data.states[0]?.id);
}
