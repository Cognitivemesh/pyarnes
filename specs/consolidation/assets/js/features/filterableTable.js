import { el } from "../util.js";
import { refreshIcons } from "../boot.js";

// Auto-applied to tables over a row threshold. Adds a search input,
// click-to-sort columns, and (when an enum-like column is detected)
// filter chips.
//
// NOTE: scheduled for HTMX migration in step 7 — search/sort/filter
// will move to /api/table and this module will shrink to attribute markup.
const TABLE_ROW_THRESHOLD = 12;

export function filterableTable(root) {
  const tables = root.querySelectorAll(".markdown-body table");
  for (const table of tables) {
    const rows = table.querySelectorAll("tbody tr");
    if (rows.length < TABLE_ROW_THRESHOLD) continue;
    if (table.dataset.specsTableEnhanced === "true") continue;
    table.dataset.specsTableEnhanced = "true";
    enhanceTable(table);
  }
}

function enhanceTable(table) {
  const rows = [...table.querySelectorAll("tbody tr")];
  const headers = [...table.querySelectorAll("thead th")];
  const columnValues = headers.map(() => new Map());
  for (const row of rows) {
    [...row.children].forEach((cell, i) => {
      if (i >= columnValues.length) return;
      const value = cell.textContent.trim();
      columnValues[i].set(value, (columnValues[i].get(value) || 0) + 1);
    });
  }
  let enumColumn = -1;
  let enumValues = [];
  columnValues.forEach((map, i) => {
    if (enumColumn !== -1) return;
    const distinct = [...map.keys()].filter((v) => v.length > 0 && v.length <= 12);
    if (distinct.length >= 2 && distinct.length <= 6 && map.size <= 6) {
      enumColumn = i;
      enumValues = distinct;
    }
  });

  let activeChip = "All";
  let query = "";
  let sortColumn = -1;
  let sortDir = "asc";

  const apply = () => {
    let visible = rows.slice();
    if (activeChip !== "All" && enumColumn >= 0) {
      visible = visible.filter((r) => r.children[enumColumn]?.textContent.trim() === activeChip);
    }
    if (query) {
      const q = query.toLowerCase();
      visible = visible.filter((r) => r.textContent.toLowerCase().includes(q));
    }
    if (sortColumn >= 0) {
      visible.sort((a, b) => {
        const av = a.children[sortColumn]?.textContent.trim() ?? "";
        const bv = b.children[sortColumn]?.textContent.trim() ?? "";
        const cmp = av.localeCompare(bv, undefined, { numeric: true });
        return sortDir === "asc" ? cmp : -cmp;
      });
    }
    const tbody = table.querySelector("tbody");
    for (const row of rows) row.style.display = visible.includes(row) ? "" : "none";
    for (const row of visible) tbody.append(row);
  };

  const search = el("input", {
    type: "search",
    placeholder: "Filter rows…",
    "aria-label": "Filter table rows",
    oninput: (e) => {
      query = e.target.value;
      apply();
    },
  });
  const searchWrap = el(
    "div",
    { class: "table-search" },
    el("i", { "data-lucide": "search", "aria-hidden": "true" }),
    search,
  );

  const chipsWrap = el("div", { class: "table-chips" });
  if (enumColumn >= 0) {
    for (const choice of ["All", ...enumValues]) {
      const chip = el(
        "button",
        {
          type: "button",
          class: "table-chip" + (choice === "All" ? " is-active" : ""),
          onclick: () => {
            activeChip = choice;
            chipsWrap.querySelectorAll(".table-chip").forEach((c) => {
              c.classList.toggle("is-active", c.textContent.trim() === choice);
            });
            apply();
          },
        },
        choice,
      );
      chipsWrap.append(chip);
    }
  }

  const toolbar = el("div", { class: "table-toolbar" }, searchWrap, chipsWrap);
  table.parentNode.insertBefore(toolbar, table);

  headers.forEach((th, i) => {
    th.dataset.sortable = "true";
    th.append(el("i", { "data-lucide": "arrow-up-down", "aria-hidden": "true" }));
    th.addEventListener("click", () => {
      if (sortColumn === i) {
        sortDir = sortDir === "asc" ? "desc" : "asc";
      } else {
        sortColumn = i;
        sortDir = "asc";
      }
      headers.forEach((h, hi) => {
        if (hi !== i) {
          delete h.dataset.sort;
        } else {
          h.dataset.sort = sortDir;
        }
      });
      apply();
    });
  });

  refreshIcons();
}
