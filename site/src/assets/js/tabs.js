// Accessible tabs (WAI-ARIA tabs pattern): arrow keys, Home/End, roving tabindex.
// Works for panels that are siblings inside the same [data-tabs] container.
// A tab may also control an external, always-visible panel (see architecture view switcher);
// in that case pass onChange and the panel visibility is left to the caller.

export function initTabs(root, onChange) {
  const tabs = [...root.querySelectorAll('[role="tab"]')];
  if (!tabs.length) return;

  const panelFor = (tab) => document.getElementById(tab.getAttribute("aria-controls"));
  const sharedPanel = new Set(tabs.map((t) => t.getAttribute("aria-controls"))).size === 1;

  function select(tab, focus = false) {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      const p = panelFor(t);
      if (p && !sharedPanel) p.hidden = !on;
    });
    if (sharedPanel) panelFor(tab)?.setAttribute("aria-labelledby", tab.id);
    if (focus) tab.focus();
    onChange?.(tab);
  }

  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (e) => {
      let next = null;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") next = tabs[(i + 1) % tabs.length];
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = tabs[(i - 1 + tabs.length) % tabs.length];
      else if (e.key === "Home") next = tabs[0];
      else if (e.key === "End") next = tabs[tabs.length - 1];
      if (next) { e.preventDefault(); select(next, true); }
    });
  });

  const initial = tabs.find((t) => t.getAttribute("aria-selected") === "true") || tabs[0];
  select(initial);
}
