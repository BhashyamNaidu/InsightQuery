// Small DOM + formatting helpers shared by the page modules. No dependencies.
// All dynamic text is inserted with textContent / createTextNode, never innerHTML,
// so recorded model output can never inject markup into the page.

export function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  append(node, children);
  return node;
}

export function append(node, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function svg(tag, attrs, ...children) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  append(node, children);
  return node;
}

export async function loadJson(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return res.json();
}

export function fmtMs(ms) {
  if (ms == null) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

export function fmtNum(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString("en-US", { maximumFractionDigits: 2 }) : String(n);
}

export function fmtDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return String(iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

const SQL_KEYWORDS = new Set(
  ("select from where group by order limit having join left right inner outer on as and or not in is null " +
   "case when then else end distinct union all with asc desc between like ilike filter over partition delete update " +
   "insert drop truncate alter create").split(" ")
);

/** Returns a <pre class="sql-block"> with lightweight, text-safe syntax colouring. */
export function sqlBlock(sql) {
  const pre = h("pre", { class: "sql-block", tabindex: "0", "aria-label": "SQL statement" });
  const code = h("code", { style: "background:none;padding:0" });
  const re = /('(?:[^']|'')*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z_0-9]*)(\s*\()?|(\s+)|(.)/g;
  let m;
  while ((m = re.exec(sql))) {
    if (m[1]) code.append(h("span", { class: "str" }, m[1]));
    else if (m[2]) code.append(h("span", { class: "num" }, m[2]));
    else if (m[3]) {
      const word = m[3];
      if (SQL_KEYWORDS.has(word.toLowerCase())) code.append(h("span", { class: "kw" }, word));
      else if (m[4]) code.append(h("span", { class: "fn" }, word));
      else code.append(word);
      if (m[4]) code.append(m[4]);
    } else code.append(m[0]);
  }
  pre.append(code);
  return pre;
}

/* ---------------- charts: small, dependency-free SVG ---------------- */

const isNum = (v) => v !== null && v !== "" && !isNaN(Number(v)) && isFinite(Number(v));

/** Decide whether result rows have a plottable shape. Returns {kind, labelKey, valueKey} or null. */
export function chartShape(rows) {
  if (!rows || rows.length < 2) return null;
  const keys = Object.keys(rows[0]);
  const valueKey = keys.find((k) => rows.every((r) => isNum(r[k])) && !/^(year|id)$/i.test(k));
  const labelKey = keys.find((k) => k !== valueKey);
  if (!valueKey || !labelKey) return null;
  const time = /month|date|week|day|year/i.test(labelKey) || rows.every((r) => /^\d{4}-\d{2}/.test(String(r[labelKey])));
  if (rows.length > 25 && !time) return null;
  return { kind: time ? "line" : "bar", labelKey, valueKey };
}

function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

const compact = (n) => (n >= 1000 ? `${+(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(Math.round(n * 100) / 100));

function monthLabel(s) {
  const m = /^(\d{4})-(\d{2})/.exec(String(s));
  if (!m) return String(s);
  return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+m[2] - 1] || String(s);
}

/** Bar or line chart for {labelKey,valueKey}. Honest axes: always starts at zero. */
export function resultChart(rows, shape, { height = 190 } = {}) {
  if (shape.kind === "line") rows = [...rows].sort((p, q) => String(p[shape.labelKey]).localeCompare(String(q[shape.labelKey])));
  const W = 560, H = height, pad = { l: 46, r: 14, t: 16, b: 40 };
  const vals = rows.map((r) => Number(r[shape.valueKey]));
  const max = niceMax(Math.max(...vals));
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const x = (i) => pad.l + (shape.kind === "line" ? (i / (rows.length - 1)) * iw : (i + 0.5) * (iw / rows.length));
  const y = (v) => pad.t + ih - (v / max) * ih;

  const root = svg("svg", {
    class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `${shape.kind === "line" ? "Line" : "Bar"} chart of ${shape.valueKey} by ${shape.labelKey}`,
  });
  for (let t = 0; t <= 4; t++) {
    const v = (max / 4) * t, yy = y(v);
    root.append(svg("line", { class: t === 0 ? "axis" : "grid", x1: pad.l, x2: W - pad.r, y1: yy, y2: yy }));
    root.append(svg("text", { x: pad.l - 8, y: yy + 4, "text-anchor": "end" }, compact(v)));
  }
  if (shape.kind === "bar") {
    const bw = Math.min(54, (iw / rows.length) * 0.62);
    rows.forEach((r, i) => {
      root.append(svg("rect", { class: "bar", x: x(i) - bw / 2, y: y(vals[i]), width: bw, height: Math.max(1, y(0) - y(vals[i])), rx: 4 }));
      root.append(svg("text", { class: "val", x: x(i), y: y(vals[i]) - 6, "text-anchor": "middle" }, compact(vals[i])));
      // wrap long category names onto two lines instead of truncating them into each other
      const words = String(r[shape.labelKey]).split(" ");
      const lines = [words.slice(0, Math.ceil(words.length / 2)).join(" "), words.slice(Math.ceil(words.length / 2)).join(" ")].filter(Boolean);
      const cut = (t) => (t.length > 13 ? t.slice(0, 12) + "…" : t);
      const label = svg("text", { x: x(i), y: H - 22, "text-anchor": "middle" });
      lines.forEach((t, k) => label.append(svg("tspan", { x: x(i), dy: k ? 12 : 0 }, cut(t))));
      root.append(label);
    });
  } else {
    const pts = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    root.append(svg("polygon", { class: "area", points: `${x(0)},${y(0)} ${pts.join(" ")} ${x(vals.length - 1)},${y(0)}` }));
    root.append(svg("polyline", { class: "line", points: pts.join(" ") }));
    vals.forEach((v, i) => {
      root.append(svg("circle", { class: "pt", cx: x(i), cy: y(v), r: 3.2 }));
      const step = rows.length > 8 ? 2 : 1;
      if (i % step === 0) root.append(svg("text", { x: x(i), y: H - 12, "text-anchor": "middle" }, monthLabel(rows[i][shape.labelKey])));
    });
  }
  return root;
}
