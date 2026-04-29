// Shared client-side utilities. No DOM mutation here — only helpers that
// other modules compose. Importable from anywhere.

export function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === false || value == null) continue;
      if (key === "class") node.className = value;
      else if (key === "html") node.innerHTML = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (key === "dataset") {
        for (const [dk, dv] of Object.entries(value)) node.dataset[dk] = dv;
      } else {
        node.setAttribute(key, value);
      }
    }
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function rafThrottle(fn) {
  let queued = false;
  return (...args) => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      fn(...args);
    });
  };
}

export function trapFocus(container) {
  const handler = (event) => {
    if (event.key !== "Tab") return;
    const focusable = container.querySelectorAll(
      "a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex='-1'])",
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  container.addEventListener("keydown", handler);
  return () => container.removeEventListener("keydown", handler);
}

export const storage = {
  get(key, fallback = null) {
    try {
      const raw = window.localStorage.getItem(`specs.${key}`);
      return raw == null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      window.localStorage.setItem(`specs.${key}`, JSON.stringify(value));
    } catch {
      /* quota or disabled — silently degrade */
    }
  },
};

export const sessionCache = {
  get(key, fallback = null) {
    try {
      const raw = window.sessionStorage.getItem(`specs.${key}`);
      return raw == null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      window.sessionStorage.setItem(`specs.${key}`, JSON.stringify(value));
    } catch {
      /* ignored */
    }
  },
};
