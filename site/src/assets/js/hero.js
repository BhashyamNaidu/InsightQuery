// Hero product preview: a compact view of one *recorded* investigation (same data as the demo).
import { h, clear, fmtMs, sqlBlock, chartShape, resultChart, fmtDate } from "./util.js";

export function renderHero(container, ex, meta) {
  clear(container);
  const r = ex.response, sl = r.stage_latency_ms || {}, sqlR = r.sql_result;
  const verdictOk = sqlR ? sqlR.validation_ok : null;

  const pipe = [
    ["Intent", true, sl.intent],
    // true = ran, false = failed, null = not used for this route (neutral, never shown as a failure)
    ["SQL generated", sqlR ? true : null, null],
    ["Validated", sqlR ? verdictOk : null, null],
    ["Executed read-only", sqlR && verdictOk ? true : null, sl.sql],
    ["Documents", r.evidence && r.evidence.length > 0 ? true : null, sl.rag],
    ["Synthesis", r.synthesis ? true : null, sl.synthesis],
    ["Audited", true, null],
  ];
  const pipeEl = h("ul", { class: "pipe", "aria-label": "Pipeline stages for this run" },
    pipe.map(([name, on, ms]) => h("li", { class: on === false ? "bad" : on ? "on" : "off" },
      on ? "✓" : on === false ? "✕" : "–", " ", name, on == null ? h("em", {}, " not used") : null, ms != null ? h("em", {}, ` ${fmtMs(ms)}`) : null)));

  const body = h("div", { class: "trace-body" }, h("p", { class: "trace-q" }, r.question), pipeEl);
  if (sqlR) body.append(sqlBlock(sqlR.executed_sql || sqlR.generated_sql));
  const shape = sqlR && sqlR.validation_ok ? chartShape(sqlR.rows) : null;
  if (shape) body.append(resultChart(sqlR.rows, shape, { height: 170 }));
  if (r.synthesis) body.append(h("p", { class: "small", style: "margin:0;color:var(--text-2)" }, r.synthesis.answer));

  container.append(h("figure", { class: "trace-card", style: "margin:0", "aria-label": "Preview of a recorded InsightQuery investigation" },
    h("div", { class: "trace-bar" }, h("span", { class: "lights", "aria-hidden": "true" }, h("i"), h("i"), h("i")),
      h("span", { class: "small", style: "font-weight:600" }, "Investigation trace"),
      h("span", { class: "rec" }, "RECORDED RUN")),
    body,
    h("figcaption", { class: "trace-foot" }, `Real output of the API · ${fmtDate(ex.recorded_at)} · ${meta.model} · not generated live`)));
}
