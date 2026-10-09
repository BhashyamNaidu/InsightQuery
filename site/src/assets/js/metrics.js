// Evidence section. Values come from data/metrics.json, which build.mjs derives from the
// repository's committed evaluation outputs (docs/*_eval_results.json) plus site/src/data/facts.json
// (hand-recorded facts, each with its source). A missing value renders "Not yet measured".

import { h, clear, svg, fmtNum, fmtDate } from "./util.js";

const pct = (x) => (x == null ? null : `${(x * 100).toFixed(x === 1 || x === 0 ? 0 : 1)}%`);

function card({ title, value, unit, what, foot, meter, sub, unmeasured }) {
  const c = h("article", { class: `metric${unmeasured ? " unmeasured" : ""}` }, h("h3", {}, title));
  c.append(h("div", { class: "value" }, unmeasured ? "Not yet measured" : value, unit ? h("small", {}, unit) : null));
  if (meter != null && !unmeasured) c.append(h("div", { class: "meter", role: "presentation" }, h("i", { style: `width:${Math.max(0, Math.min(1, meter)) * 100}%` })));
  if (sub) c.append(sub);
  c.append(h("p", { class: "what" }, what));
  c.append(h("p", { class: "foot" }, foot));
  return c;
}

export function renderMetrics(m) {
  const grid = document.getElementById("metric-grid");
  clear(grid);
  const when = (iso) => fmtDate(iso);
  const f = m.facts;

  grid.append(
    card({
      title: "Automated tests", value: String(f.tests.passed), unit: `passed · ${f.tests.failed} failed · ${f.tests.skipped} skipped`,
      what: "Unit, API, real-PostgreSQL integration and live-LLM adversarial tests.",
      foot: h("span", {}, h("b", {}, `Full local run, ${when(f.tests.date)}. `), "GitHub Actions runs the same suite with the LLM off, so live-LLM tests skip there."),
    }),
    card({
      title: "RAG Recall@5", value: m.rag.recall_at_5.toFixed(2), unit: `n=${m.rag.n}`, meter: m.rag.recall_at_5,
      what: "How often the expected document appears in the top 5 retrieved results.",
      foot: h("span", {}, h("b", {}, `${when(m.evaluated_at)}. `), "15 hand-written questions, one per document: shows the pipeline works, not general recall."),
    }),
    card({
      title: "RAG MRR", value: m.rag.mrr.toFixed(3), unit: `n=${m.rag.n}`, meter: m.rag.mrr,
      what: "Mean reciprocal rank of the expected document: rewards ranking it first.",
      foot: h("span", {}, h("b", {}, "14 of 15 at rank 1; "), "one near-miss at rank 3 (ward vs. community area)."),
    }),
    card({
      title: "Intent accuracy", value: pct(m.intent.accuracy), unit: `${m.intent.correct}/${m.intent.n}`, meter: m.intent.accuracy,
      what: "Whether the model routes a question to sql / rag / hybrid / rejected correctly.",
      foot: h("span", {}, h("b", {}, `${when(m.evaluated_at)}, ${m.model}. `), `5 questions per route. The previous run scored ${pct(f.intent_previous)}; that gap is one question and is not evidence of improvement.`),
    }),
    card({
      title: "Malicious SQL blocked", value: `${m.nl2sql.malicious_blocked}/${m.nl2sql.n_malicious}`, unit: "none executed", meter: m.nl2sql.malicious_blocked_rate,
      what: "Injection, destructive and unauthorized-access prompts that never reached the database.",
      foot: h("span", {}, h("b", {}, `${when(m.evaluated_at)}. `), "The model declined or the validator rejected each. Also 7/7 in every earlier run of this configuration. A finite set, not a proof."),
    }),
    card({
      title: "Legitimate questions allowed", value: `${m.nl2sql.legit_allowed}/${m.nl2sql.n_legit}`, meter: m.nl2sql.legit_allowed / m.nl2sql.n_legit,
      what: "Reasonable analytics questions whose SQL passed validation.",
      foot: h("span", {}, h("b", {}, "The one miss "), "was a query that referenced no table, so the validator correctly rejected it."),
    }),
    card({
      title: "SQL execution success", value: `${m.nl2sql.exec_ok}/${m.nl2sql.n_validated}`, unit: pct(m.nl2sql.execution_success_rate), meter: m.nl2sql.execution_success_rate,
      what: "Of queries that passed validation, how many ran in PostgreSQL without error.",
      foot: h("span", {}, h("b", {}, "Not semantic correctness. "), "A manual review of an earlier run found 4 of 10 executed queries returned wrong answers. See the ablation below."),
    }),
    card({
      title: "End-to-end latency", value: `${(m.e2e.avg_ms / 1000).toFixed(1)} s`, unit: "average",
      sub: h("div", { class: "metric-subgrid" },
        h("div", {}, h("b", {}, `${(m.e2e.p50_ms / 1000).toFixed(1)} s`), h("span", {}, "p50")),
        h("div", {}, h("b", {}, `${(m.e2e.p95_ms / 1000).toFixed(1)} s`), h("span", {}, "p95")),
        h("div", {}, h("b", {}, `${m.e2e.n_succeeded}/${m.e2e.n}`), h("span", {}, "succeeded"))),
      what: "Question to full answer, with a 3B model on CPU. Synthesis dominates.",
      foot: h("span", {}, h("b", {}, `n=${m.e2e.n}: `), "too few runs for a statistically robust percentile. A hosted model would likely be much faster; that has not been measured."),
    }),
    card({
      title: "Dataset", value: fmtNum(f.dataset.rows), unit: "records",
      sub: h("div", { class: "metric-subgrid" },
        h("div", {}, h("b", {}, f.dataset.year), h("span", {}, "year")),
        h("div", {}, h("b", {}, f.dataset.documents), h("span", {}, "documents")),
        h("div", {}, h("b", {}, f.dataset.chunks), h("span", {}, "chunks"))),
      what: "Chicago Police Department reported incidents (open data) and the curated corpus.",
      foot: h("span", {}, h("b", {}, `Counted in the database ${when(f.dataset.verified)}. `), "Preliminary data, block-level locations."),
    }),
  );

  renderAblation(m.facts.ablation);
}

function renderAblation(a) {
  const host = document.getElementById("ablation-plot");
  clear(host);
  const W = 720, rowH = 62, top = 30, left = 214, right = 24, H = top + rowH * a.arms.length + 40;
  const x = (v) => left + (v / 10) * (W - left - right);
  const root = svg("svg", { class: "strip", viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Strip plot: out of 10 legitimate questions, how many executed without error in each run, for three configurations. The ranges overlap heavily." });

  for (let v = 0; v <= 10; v += 2) {
    root.append(svg("line", { class: "gridl", x1: x(v), x2: x(v), y1: top - 8, y2: H - 30 }));
    root.append(svg("text", { x: x(v), y: H - 12, "text-anchor": "middle" }, String(v)));
  }
  root.append(svg("text", { x: left, y: 14 }, "Legitimate questions that executed without error (of 10), one dot per run"));

  // shaded band: the full range the *same* old configuration produced
  const all = a.arms[0].runs.concat(a.arms[0].reference || []);
  const lo = Math.min(...all), hi = Math.max(...all);
  root.append(svg("rect", { class: "band", x: x(lo) - 6, y: top - 6, width: x(hi) - x(lo) + 12, height: rowH * a.arms.length - 4, rx: 8 }));

  a.arms.forEach((arm, i) => {
    const cy = top + i * rowH + rowH / 2 - 6;
    root.append(svg("text", { class: "lab", x: 0, y: cy - 2 }, arm.label));
    root.append(svg("text", { x: 0, y: cy + 15 }, arm.sub));
    root.append(svg("line", { class: "track", x1: x(0), x2: x(10), y1: cy, y2: cy }));
    // jitter identical values vertically so no dot hides another
    const seen = {};
    const place = (v, cls) => {
      const k = seen[v] = (seen[v] || 0) + 1;
      root.append(svg("circle", { class: `dot ${cls}`, cx: x(v), cy: cy - (k - 1) * 11, r: 6 }, svg("title", {}, `${v} of 10`)));
    };
    arm.runs.forEach((v) => place(v, ""));
    (arm.full_eval || []).forEach((v) => place(v, "full"));
    (arm.reference || []).forEach((v) => place(v, "ref"));
    const vals = arm.runs;
    const mean = vals.reduce((s, v) => s + v, 0) / vals.length;
    root.append(svg("line", { class: "mean", x1: x(mean), x2: x(mean), y1: cy + 10, y2: cy + 22 }));
    root.append(svg("text", { x: x(mean), y: cy + 34, "text-anchor": "middle" }, `mean ${mean.toFixed(2)} (n=${vals.length})`));
  });
  host.append(root);
  host.append(h("p", { class: "small muted", style: "margin:8px 0 0" },
    "Blue: ablation runs. Teal: full evaluation runs of the shipped configuration. Amber: the original single baseline. Shaded: the range the old configuration alone produced."));

  const notes = document.getElementById("ablation-notes");
  clear(notes);
  a.notes.forEach((t) => notes.append(h("li", {}, t)));
}
