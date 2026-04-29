import { el, trapFocus } from "../util.js";
import { refreshIcons } from "../boot.js";

// D3-backed dep-graph drawer. Force-directed layout with zoom + drag, tag-aware
// search, type-coloured nodes, and a side detail panel powered by index.spec_headers.
//
// Two open paths:
//   - topbar [data-specs-action='open-dep-graph'] click  → open(currentSlug)
//   - window 'dep-graph-open' event (Alpine $dispatch from spec-card buttons)
//     with detail.focus = "<NN-slug>"                    → open(detail.focus)
//
// Self-disables (no throw) if the data island lacks deps, the page has no
// trigger AND no event source, or the d3 CDN didn't load.
export function depGraphDrawer(root, index) {
  if (!index?.deps || Object.keys(index.deps).length === 0) return;
  if (typeof window.d3 === "undefined") {
    console.warn("specs.js: d3 not loaded — dep-graph drawer disabled");
    return;
  }

  const trigger = root.querySelector("[data-specs-action='open-dep-graph']");
  if (trigger) trigger.removeAttribute("hidden");

  // ---- Slug + header lookups -------------------------------------------------
  // Node ids are 2-digit prefixes (`01`); pages/headers are `01-package-structure`.
  const headers = index.spec_headers ?? {};
  const slugFor = (id) => {
    const page = index.pages.find((p) => p.slug.startsWith(`${id}-`));
    return page ? page.slug : id;
  };
  const titleFor = (id) => headers[slugFor(id)]?.title ?? slugFor(id);
  const hrefFor = (id) => index.pages.find((p) => p.slug === slugFor(id))?.href ?? null;
  // Strip leading "<package> — " / "<package>: " prefix and clip overly long
  // titles so node labels don't collide with neighbouring nodes.
  const shortenLabel = (title) => {
    const stripped = (title ?? "").replace(/^[^—:]+(—|:)\s*/, "");
    return stripped.length > 28 ? stripped.slice(0, 27) + "…" : stripped;
  };

  // ---- Nodes + edges ---------------------------------------------------------
  const ids = new Set([...Object.keys(index.deps), ...Object.values(index.deps).flat()]);
  const nodes = [...ids].sort().map((id) => {
    const slug = slugFor(id);
    const header = headers[slug] ?? {};
    return {
      id,
      slug,
      title: header.title ?? slug,
      type: header.type ?? null,
      status: header.status ?? null,
      tags: Array.isArray(header.tags) ? [...header.tags] : [],
      tagSet: new Set(Array.isArray(header.tags) ? header.tags : []),
      header,
    };
  });
  const edges = [];
  for (const [src, targets] of Object.entries(index.deps)) {
    for (const tgt of targets) edges.push({ source: src, target: tgt });
  }

  // ---- Drawer chrome ---------------------------------------------------------
  const searchInput = el("input", {
    type: "search",
    class: "dep-graph-search-input",
    placeholder: "Search by id, title, or tag…",
    "aria-label": "Search dep-graph nodes",
  });
  const topicsStrip = el("div", { class: "dep-graph-topics", role: "group", "aria-label": "Filter by topic" });
  const svg = window.d3
    .create("svg")
    .attr("class", "dep-graph-svg")
    .attr("role", "img")
    .attr("aria-label", "Spec dependency graph");
  const detailEl = el("aside", { class: "dep-graph-detail", "aria-hidden": "true" });

  const drawer = el(
    "aside",
    { class: "dep-graph-drawer", "aria-hidden": "true" },
    el(
      "div",
      { class: "dep-graph-header" },
      el("p", { class: "dep-graph-title" }, "Spec dependency graph"),
      el(
        "button",
        { type: "button", class: "dep-graph-close", "aria-label": "Close drawer" },
        el("i", { "data-lucide": "x", "aria-hidden": "true" }),
      ),
    ),
    el(
      "div",
      { class: "dep-graph-body" },
      el("div", { class: "dep-graph-search" }, searchInput),
      topicsStrip,
      el("div", { class: "dep-graph-canvas" }, svg.node()),
      detailEl,
    ),
  );
  document.body.append(drawer);

  // Topic chips
  const topicChips = Array.isArray(index.topic_chips) ? index.topic_chips : [];
  const activeTopics = new Set();
  for (const entry of topicChips) {
    const [tag, count] = entry;
    const chip = el(
      "button",
      {
        type: "button",
        class: "dep-graph-topic-chip",
        dataset: { tag },
      },
      el("span", { class: "dep-graph-topic-name" }, tag),
      el("span", { class: "dep-graph-topic-count" }, String(count)),
    );
    chip.addEventListener("click", () => {
      if (activeTopics.has(tag)) activeTopics.delete(tag);
      else activeTopics.add(tag);
      chip.classList.toggle("is-active", activeTopics.has(tag));
      applyDim();
    });
    topicsStrip.append(chip);
  }

  // ---- D3 setup --------------------------------------------------------------
  const d3 = window.d3;
  const width = 520;
  const height = 480;
  svg.attr("viewBox", `0 0 ${width} ${height}`);

  const viewport = svg.append("g").attr("class", "dep-graph-viewport");
  const linkSel = viewport
    .append("g")
    .attr("class", "edges")
    .selectAll("line")
    .data(edges)
    .enter()
    .append("line")
    .attr("class", "edge");

  const nodeSel = viewport
    .append("g")
    .attr("class", "nodes")
    .selectAll("g")
    .data(nodes)
    .enter()
    .append("g")
    .attr("class", "node")
    .attr("tabindex", "0")
    .attr("aria-label", (n) => n.title)
    .each(function (n) {
      this.dataset.id = n.id;
      if (n.type) this.dataset.type = n.type;
      if (index.current && n.slug === index.current) this.classList.add("is-current");
    });
  nodeSel.append("circle").attr("r", 16);
  nodeSel
    .append("text")
    .attr("class", "dep-graph-node-id")
    .attr("text-anchor", "middle")
    .attr("dy", 4)
    .text((n) => n.id);
  // Title label, wrapped in <a> so clicks navigate to the spec — turns the
  // graph into a hyperlinked map without losing select-on-circle behavior.
  const labelLink = nodeSel
    .append("a")
    .attr("class", "dep-graph-node-link")
    .attr("href", (n) => hrefFor(n.id) ?? null)
    .attr("target", "_self");
  labelLink
    .append("text")
    .attr("class", "dep-graph-node-label")
    .attr("text-anchor", "start")
    .attr("dx", 22)
    .attr("dy", 4)
    .text((n) => shortenLabel(n.title));

  const sim = d3
    .forceSimulation(nodes)
    .force("link", d3.forceLink(edges).id((n) => n.id).distance(80))
    .force("charge", d3.forceManyBody().strength(-260))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide(40))
    .on("tick", () => {
      linkSel
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);
      nodeSel.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

  // Pan + zoom
  const zoom = d3
    .zoom()
    .scaleExtent([0.4, 4])
    .on("zoom", (event) => viewport.attr("transform", event.transform));
  svg.call(zoom);

  // Drag — release fx/fy on end so layout stays alive.
  const drag = d3
    .drag()
    .on("start", (event, d) => {
      if (!event.active) sim.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    })
    .on("drag", (event, d) => {
      d.fx = event.x;
      d.fy = event.y;
    })
    .on("end", (event, d) => {
      if (!event.active) sim.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    });
  nodeSel.call(drag);

  // ---- Highlight + dim -------------------------------------------------------
  let selectedId = null;
  const highlight = (id) => {
    linkSel.classed("is-related", (e) => id != null && (sourceId(e) === id || targetId(e) === id));
    nodeSel.classed("is-active", (n) => n.id === id);
    nodeSel.classed(
      "is-related",
      (n) =>
        id != null &&
        edges.some(
          (e) =>
            (sourceId(e) === id && targetId(e) === n.id) ||
            (targetId(e) === id && sourceId(e) === n.id),
        ),
    );
  };
  const sourceId = (e) => (typeof e.source === "object" ? e.source.id : e.source);
  const targetId = (e) => (typeof e.target === "object" ? e.target.id : e.target);

  const matchesQuery = (n, query) => {
    if (!query) return true;
    const q = query.toLowerCase();
    if (n.id.toLowerCase().includes(q)) return true;
    if ((n.title ?? "").toLowerCase().includes(q)) return true;
    return n.tags.some((t) => t.toLowerCase().includes(q));
  };
  const matchesTopics = (n) => {
    if (activeTopics.size === 0) return true;
    for (const t of activeTopics) if (n.tagSet.has(t)) return true;
    return false;
  };
  const applyDim = () => {
    const q = searchInput.value.trim();
    const visible = new Set(nodes.filter((n) => matchesQuery(n, q) && matchesTopics(n)).map((n) => n.id));
    nodeSel.classed("is-dimmed", (n) => !visible.has(n.id));
    linkSel.classed("is-dimmed", (e) => !visible.has(sourceId(e)) || !visible.has(targetId(e)));
  };
  searchInput.addEventListener("input", applyDim);

  // ---- Detail panel ----------------------------------------------------------
  const renderDetail = (id) => {
    detailEl.replaceChildren();
    if (!id) {
      detailEl.classList.remove("is-open");
      detailEl.setAttribute("aria-hidden", "true");
      return;
    }
    const node = nodes.find((n) => n.id === id);
    if (!node) return;
    const h = node.header ?? {};

    const head = el(
      "header",
      { class: "dep-graph-detail-head" },
      el("h3", { class: "dep-graph-detail-title" }, node.title),
      el(
        "div",
        { class: "dep-graph-detail-badges" },
        node.status &&
          el("span", { class: `spec-status spec-status--${node.status}` }, node.status),
        node.type &&
          el("span", { class: "spec-type-chip", dataset: { type: node.type } }, node.type),
      ),
    );
    detailEl.append(head);

    if (node.tags.length) {
      const tagWrap = el(
        "div",
        { class: "dep-graph-detail-tags" },
        ...node.tags.map((t) => el("span", { class: "spec-tag" }, t)),
      );
      detailEl.append(tagWrap);
    }

    const refList = (label, items) => {
      if (!items?.length) return null;
      return el(
        "div",
        { class: "dep-graph-detail-row" },
        el("p", { class: "dep-graph-detail-label" }, label),
        el(
          "ul",
          { class: "dep-graph-detail-list" },
          ...items.map((v) => {
            const title = titleFor(v);
            const href = hrefFor(v);
            const text = title && title !== v ? `${v} — ${title}` : v;
            return el("li", null, href ? el("a", { href }, text) : text);
          }),
        ),
      );
    };
    const rows = [
      refList("Owns", h.owns),
      refList("Depends on", h.depends_on),
      refList("Extends", h.extends),
      refList("Supersedes", h.supersedes),
      refList("Read after", h.read_after),
      refList("Read before", h.read_before),
      refList("Not owned here", h.not_owned_here),
    ].filter(Boolean);
    if (rows.length) {
      detailEl.append(el("div", { class: "dep-graph-detail-rows" }, ...rows));
    }
    if (h.last_reviewed) {
      detailEl.append(
        el(
          "p",
          { class: "dep-graph-detail-meta" },
          `Last reviewed: ${h.last_reviewed}`,
        ),
      );
    }
    const href = hrefFor(id);
    if (href) {
      detailEl.append(
        el(
          "a",
          { href, class: "dep-graph-detail-open" },
          el("i", { "data-lucide": "external-link", "aria-hidden": "true" }),
          el("span", null, "Open spec"),
        ),
      );
    }
    detailEl.classList.add("is-open");
    detailEl.setAttribute("aria-hidden", "false");
    refreshIcons();
  };

  // Node interactions
  nodeSel
    .on("mouseenter", (_event, d) => highlight(d.id))
    .on("mouseleave", () => highlight(selectedId))
    .on("focus", (_event, d) => highlight(d.id))
    .on("click", (_event, d) => {
      selectedId = d.id;
      highlight(d.id);
      renderDetail(d.id);
    });

  // ---- Open / close ---------------------------------------------------------
  const closeBtn = drawer.querySelector(".dep-graph-close");
  let releaseFocus = null;
  const open = (focusSlugOrId = null) => {
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    sim.alpha(0.6).restart();
    releaseFocus = trapFocus(drawer);
    if (focusSlugOrId) {
      // Accept either the 2-digit id or the full slug.
      const id = /^\d{2}$/.test(focusSlugOrId)
        ? focusSlugOrId
        : focusSlugOrId.split("-", 1)[0];
      const n = nodes.find((x) => x.id === id);
      if (n) {
        selectedId = id;
        highlight(id);
        renderDetail(id);
        // Re-center the viewport on the focused node once layout settles.
        sim.on("end.focus", () => {
          if (n.x == null) return;
          const transform = d3.zoomIdentity
            .translate(width / 2 - n.x, height / 2 - n.y)
            .scale(1);
          svg.transition().duration(400).call(zoom.transform, transform);
          sim.on("end.focus", null);
        });
      }
    }
    closeBtn.focus();
  };
  const close = () => {
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    sim.stop();
    releaseFocus?.();
    releaseFocus = null;
    if (trigger) trigger.focus();
  };
  if (trigger) trigger.addEventListener("click", () => open(index.current));
  closeBtn.addEventListener("click", close);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawer.classList.contains("is-open")) close();
  });
  // Spec-card $dispatch('dep-graph-open', { focus: '<slug>' })
  window.addEventListener("dep-graph-open", (event) => open(event.detail?.focus));

  refreshIcons();
}
