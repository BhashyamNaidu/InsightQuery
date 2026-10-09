// Investigation lab: renders a *recorded* InvestigateResponse as eight stages.
// Nothing here calls a model or a database. Every field shown is read from the recorded
// API response; text that is not part of that response (the "how to read this" notes and the
// reviewer notes) is visually separated and labelled as such.

import { h, clear, fmtMs, sqlBlock, chartShape, resultChart, fmtDate } from "./util.js";

const ROUTE_LABEL = { sql: "SQL analytics", rag: "Document retrieval", hybrid: "SQL + documents", rejected: "Out of scope" };

const VALIDATOR_RULES = [
  "exactly one statement, and it must be a SELECT (or UNION of SELECTs)",
  "no SQL comments",
  "only the four allow-listed tables; no information_schema / pg_catalog",
  "only known columns",
  "function deny-list (pg_sleep, dblink, pg_read_file, …)",
  "no locking clauses; a LIMIT is enforced (max 200)",
];

const HOW = {
  question: "The API accepts free text (up to 2,000 characters) and gives the run a request ID. That ID follows it into the audit log.",
  intent: "A first model call decides what kind of question this is: numbers from the database (sql), explanation from documents (rag), both (hybrid), or out of scope (rejected). If its reply can't be parsed, the system falls back to hybrid instead of failing.",
  sql: "A second model call writes a SQL query from the question and the table schema. It is treated as untrusted text: it has not been run, and nothing has checked it yet.",
  validate: "Before anything touches the database, the SQL is parsed into a syntax tree and checked against explicit rules. A rejection is final: the query is logged and never executed or “repaired”.",
  execute: "Only validated SQL reaches PostgreSQL, and only through a role that can read four tables and nothing else. The rows are computed by the database, not by the model.",
  evidence: "Methodology and caveats come from a small curated document set. The question is embedded locally and compared with stored passages by cosine similarity in pgvector.",
  system: "No model call was made here. When the SQL safety validator blocks a request and there are no documents to explain, the system returns fixed text stating what happened, instead of asking a model to interpret an empty result. A blocked query is not a query that returned zero rows.",
  synth: "The model is given only the question, the SQL rows and the retrieved passages, and asked to explain them. It may be wrong, so its citations are checked against the passages that were actually retrieved.",
  audit: "Every run is written to a query_log table: the question, route, SQL (including any repaired attempt and the database error), verdict, row count, timings and model. That is what makes a result inspectable afterwards.",
};

const tag = (cls, text) => h("span", { class: `prov ${cls}` }, text);
const chev = () => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 16 16"); s.setAttribute("class", "chev"); s.setAttribute("aria-hidden", "true");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("d", "M6 3l5 5-5 5"); p.setAttribute("fill", "none"); p.setAttribute("stroke", "currentColor"); p.setAttribute("stroke-width", "1.8");
  p.setAttribute("stroke-linecap", "round"); p.setAttribute("stroke-linejoin", "round");
  s.append(p);
  return s;
};

function stage(n, title, summary, state, latency, body) {
  const d = h("details", { class: "stage", dataset: { state } });
  d.append(h("summary", {},
    h("span", { class: "stage-num", "aria-hidden": "true" }, state === "ok" ? "✓" : state === "bad" ? "!" : String(n)),
    h("span", { class: "head" }, h("h3", {}, `${n}. ${title}`), h("p", {}, summary)),
    h("span", { class: "tail" }, latency != null ? h("span", { class: "t" }, fmtMs(latency)) : null, chev())
  ));
  d.append(h("div", { class: "stage-body" }, body));
  return d;
}

const how = (text) => h("p", { class: "how" }, h("strong", {}, "How to read this. "), text);
const skipped = (n, title, why) => stage(n, title, why, "skipped", null, [h("p", { class: "skip-note" }, why)]);

function rowsTable(rows) {
  const keys = Object.keys(rows[0] || {});
  const shown = rows.slice(0, 12);
  const table = h("table", { class: "rows-table" },
    h("thead", {}, h("tr", {}, keys.map((k) => h("th", { scope: "col" }, k)))),
    h("tbody", {}, shown.map((r) => h("tr", {}, keys.map((k) => {
      const v = r[k];
      const isNum = typeof v === "number";
      return h("td", { class: isNum ? "num" : "" }, v == null ? "—" : isNum ? v.toLocaleString("en-US") : String(v).replace(/T00:00:00$/, ""));
    }))))
  );
  return h("div", {}, h("div", { class: "table-scroll" }, table),
    rows.length > shown.length ? h("p", { class: "small muted" }, `Showing ${shown.length} of ${rows.length} rows.`) : null);
}

export function buildStages(ex, meta) {
  const r = ex.response;
  const sl = r.stage_latency_ms || {};
  const sqlR = r.sql_result;
  const stages = [];

  stages.push(stage(1, "Question received", `${r.question.length} characters · request ${r.request_id.slice(0, 8)}…`, "ok", null, [
    how(HOW.question),
    h("dl", { class: "kv" }, h("dt", {}, "Question"), h("dd", {}, r.question), h("dt", {}, "Request ID"), h("dd", {}, h("code", {}, r.request_id))),
  ]));

  stages.push(stage(2, "Intent and route", `${ROUTE_LABEL[r.route] || r.route} — ${r.intent_reasoning || "no reasoning returned"}`, "ok", sl.intent, [
    how(HOW.intent),
    h("div", {}, h("h4", {}, "Route chosen ", tag("prov-llm", "LLM-generated")),
      h("p", {}, h("span", { class: "route-pill", dataset: { route: r.route } }, r.route), " ", r.intent_reasoning || "")),
  ]));

  if (!sqlR) {
    stages.push(skipped(3, "SQL generation", "Not used: this question is answered from documents, so no SQL was generated."));
    stages.push(skipped(4, "SQL safety validation", "Not used: there was no SQL to validate."));
    stages.push(skipped(5, "Database execution", "Not used: nothing was executed against the database for this question."));
  } else {
    const first = sqlR.repaired && sqlR.first_attempt_sql ? sqlR.first_attempt_sql : sqlR.generated_sql;
    const body3 = [
      how(HOW.sql),
      h("div", {}, h("h4", {}, sqlR.repaired ? "Original SQL proposed by the model " : "SQL proposed by the model ", tag("prov-llm", "LLM-generated · untrusted")), sqlBlock(first || "")),
    ];
    if (sqlR.repaired) {
      body3.push(
        h("div", { class: "callout bad" }, h("strong", {}, "PostgreSQL rejected the original. "), "The error returned was:",
          h("pre", { class: "sql-block", style: "margin-top:8px;white-space:pre-wrap" }, sqlR.first_attempt_error || "")),
        h("div", {}, h("h4", {}, "Repaired SQL — the model's one allowed retry ", tag("prov-llm", "LLM-generated · untrusted")), sqlBlock(sqlR.generated_sql || "")));
    }
    if (sl.sql != null) body3.push(h("p", { class: "small muted" }, `The ${fmtMs(sl.sql)} shown covers generation, validation, execution${sqlR.repaired ? " and the repair" : ""} together; the API reports them as one stage.`));
    stages.push(stage(3, sqlR.repaired ? "SQL generation and one repair" : "SQL generation",
      sqlR.repaired ? "The first query failed in PostgreSQL; the model regenerated it once" : (first || "").replace(/\s+/g, " ").slice(0, 110) + ((first || "").length > 110 ? "…" : ""),
      sqlR.repaired ? "bad" : "ok", sl.sql, body3));

    const ok = sqlR.validation_ok;
    stages.push(stage(4, sqlR.repaired ? "SQL safety validation (of the repaired query)" : "SQL safety validation", ok ? "Accepted" : `Rejected — ${sqlR.rejection_reason}`, ok ? "ok" : "bad", null, [
      how(HOW.validate),
      sqlR.repaired ? h("p", { class: "skip-note" }, "The original query passed this gate and then failed inside PostgreSQL. The repaired query is a new untrusted output, so it was validated again from scratch.") : null,
      h("div", { class: `callout ${ok ? "ok" : "bad"}` }, ok
        ? h("span", {}, h("strong", {}, "Accepted. "), `The ${sqlR.repaired ? "repaired " : ""}statement passed every rule below.`)
        : h("span", {}, h("strong", {}, "Rejected. "), sqlR.rejection_reason, sqlR.repaired
          ? " The repaired statement was never executed, and there is no second retry."
          : " The statement was not executed and was not sent back to the model to be rewritten.")),
      h("div", {}, h("h4", {}, "Rules applied by ", h("code", {}, "app/nlsql/validator.py")),
        h("ul", { class: "chips" }, VALIDATOR_RULES.map((t) => h("li", {}, t)))),
    ]));

    if (!ok) {
      stages.push(skipped(5, "Database execution", "Skipped: the validator rejected the query, so nothing was sent to PostgreSQL."));
    } else {
      const shape = chartShape(sqlR.rows);
      const body = [how(HOW.execute)];
      body.push(h("div", {}, h("h4", {}, `Result · ${sqlR.row_count} row${sqlR.row_count === 1 ? "" : "s"} `, tag("prov-derived", "Derived analytics")),
        sqlR.rows.length ? rowsTable(sqlR.rows) : h("p", { class: "skip-note" }, "The query returned no rows.")));
      if (shape) body.push(h("div", {}, h("h4", {}, `Chart of ${shape.valueKey} by ${shape.labelKey}`), resultChart(sqlR.rows, shape),
        shape.kind === "line" ? h("p", { class: "small muted" }, "Drawn in date order. The table above keeps the order PostgreSQL returned the rows in.") : null));
      if (ex.verified) body.push(h("div", { class: "callout ok" }, h("strong", {}, "Independently verified (not produced by the system). "), ex.verified));
      if (ex.reviewer_check) body.push(h("div", { class: "callout bad" }, h("strong", {}, "Reviewer check (not produced by the system). "), ex.reviewer_check));
      if (sqlR.executed_sql && sqlR.executed_sql !== sqlR.generated_sql)
        body.push(h("div", {}, h("h4", {}, "SQL actually executed"), sqlBlock(sqlR.executed_sql)));
      const summary = sqlR.row_count === 0 ? "Executed; 0 rows returned" : `Executed read-only; ${sqlR.row_count} row${sqlR.row_count === 1 ? "" : "s"} returned`;
      stages.push(stage(5, "Database execution and results", summary, "ok", null, body));
    }
  }

  if (!r.evidence || !r.evidence.length) {
    stages.push(skipped(6, "Retrieved documentary evidence", r.route === "sql"
      ? "Not used: this question is answered from the database alone, so no documents were retrieved."
      : "No passages were retrieved for this run."));
  } else {
    stages.push(stage(6, "Retrieved documentary evidence", `${r.evidence.length} passages from ${new Set(r.evidence.map((e) => e.document_title)).size} documents`, "ok", sl.rag, [
      how(HOW.evidence),
      ...r.evidence.map((e) => h("div", { class: "evidence" },
        h("header", {}, e.document_title, h("span", {}, `cosine similarity ${e.similarity.toFixed(3)}`)),
        h("p", {}, e.content))),
      h("p", { class: "small muted" }, "Similarity is not probability of relevance; it ranks passages against each other."),
    ]));
  }

  const s = r.synthesis;
  if (!s) {
    stages.push(skipped(7, "Evidence-grounded synthesis", "No answer was synthesized for this run."));
  } else {
    // No "synthesis" latency means the response was written by the system, not by a model.
    const modelRan = sl.synthesis != null;
    const body = [
      how(modelRan ? HOW.synth : HOW.system),
      h("div", {}, h("h4", {}, "Answer ", modelRan ? tag("prov-llm", "LLM-generated") : tag("prov-system", "System message · no LLM call")), h("p", { class: modelRan ? "answer" : "answer system" }, s.answer)),
      h("dl", { class: "kv" },
        h("dt", {}, "Confidence"), h("dd", {}, modelRan ? `${s.confidence} (self-reported by the model)` : `${s.confidence} (set by the system: it describes what the system did, not a database result)`),
        h("dt", {}, "Citations kept"), h("dd", {}, s.citations.length ? s.citations.join("; ") : "none")),
    ];
    const rn = ex.reviewer_note;
    if (rn) body.push(h("div", { class: `callout ${rn.tone}` }, h("strong", {}, "Reviewer note (not produced by the system). "), rn.text));
    stages.push(stage(7, modelRan ? "Evidence-grounded synthesis" : "Response (no model call)", s.answer.length > 120 ? s.answer.slice(0, 117) + "…" : s.answer, rn && rn.tone === "bad" ? "bad" : "ok", sl.synthesis, body));
  }

  const total = r.latency_ms;
  const maxStage = Math.max(...Object.values(sl), 1);
  const auditBody = [
    how(HOW.audit),
    h("dl", { class: "kv" },
      h("dt", {}, "Request ID"), h("dd", {}, h("code", {}, r.request_id)),
      h("dt", {}, "Audit record"), h("dd", {}, "written to query_log (every run is logged, including rejected ones)"),
      h("dt", {}, "Total latency"), h("dd", {}, fmtMs(total)),
      h("dt", {}, "Model"), h("dd", {}, `${meta.model} via ${meta.provider}, ${meta.hardware}`),
      h("dt", {}, "Recorded"), h("dd", {}, fmtDate(ex.recorded_at))),
    h("div", { class: "stage-latency" }, h("h4", {}, "Per-stage latency"),
      Object.entries(sl).map(([k, v]) => h("div", { class: "lat-row" },
        h("span", {}, k), h("span", { class: "bar-track" }, h("span", { class: "bar", style: `display:block;width:${Math.max(2, (v / maxStage) * 100)}%` })), h("span", {}, fmtMs(v))))),
  ];
  if (s && s.limitations && s.limitations.length)
    auditBody.push(h("div", {}, h("h4", {}, "Limitations returned with the answer ", (sl.synthesis != null ? tag("prov-llm", "LLM-generated + system notes") : tag("prov-system", "System message"))), h("ul", { class: "chips" }, s.limitations.map((t) => h("li", {}, t)))));
  stages.push(stage(8, "Audit trail and limitations", `${fmtMs(total)} total · logged as ${r.request_id.slice(0, 8)}…`, "ok", null, auditBody));

  return stages;
}

export function initDemo(data) {
  const { meta, examples } = data;
  const list = document.getElementById("demo-examples");
  const stagesEl = document.getElementById("demo-trace");
  const titleEl = document.getElementById("demo-trace-title");
  const statusEl = document.getElementById("demo-status");
  const input = document.getElementById("demo-input");
  const form = document.getElementById("demo-form");
  const walkBtn = document.getElementById("demo-walk");
  const toggleBtn = document.getElementById("demo-toggle");
  const recModel = document.getElementById("rec-model");
  const selNote = document.getElementById("selection-note");
  if (selNote && meta.selection_note) selNote.textContent = meta.selection_note;
  if (recModel) recModel.textContent = `${meta.model} via ${meta.provider}, ${meta.hardware}`;

  let current = null;
  let step = -1;

  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  const stageNodes = () => [...stagesEl.querySelectorAll(":scope > li > details")];

  function setWalk(i) {
    const nodes = stageNodes();
    nodes.forEach((d, idx) => {
      d.classList.toggle("current", idx === i);
      if (i >= 0) d.open = idx === i;
    });
    step = i;
    if (i >= 0 && nodes[i]) nodes[i].scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    walkBtn.textContent = i < 0 ? "Walk through" : i >= nodes.length - 1 ? "Restart walk-through" : `Next stage (${i + 2}/${nodes.length})`;
    toggleBtn.textContent = "Expand all";
  }

  function show(ex, { focus = false } = {}) {
    current = ex;
    statusEl.textContent = ""; statusEl.className = "demo-status";
    list.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === ex.id)));
    clear(titleEl);
    titleEl.append(ex.response.question, h("small", {}, `Recorded ${fmtDate(ex.recorded_at)} · replay of a real run, not generated live · ${meta.model}`));
    clear(stagesEl);
    for (const d of buildStages(ex, meta)) stagesEl.append(h("li", {}, d));
    // Open the most informative stage by default: the result/answer, so the page is never an empty list of rows.
    const nodes = stageNodes();
    const open = nodes.findIndex((d) => /^(5|7)\./.test(d.querySelector("h3").textContent) && d.dataset.state !== "skipped");
    if (open >= 0) nodes[open].open = true;
    step = -1;
    walkBtn.textContent = "Walk through";
    toggleBtn.textContent = "Expand all";
    if (focus) titleEl.focus({ preventScroll: true });
  }

  for (const ex of examples) {
    const btn = h("button", { class: "example-btn", type: "button", "aria-pressed": "false", dataset: { id: ex.id } },
      h("span", { class: "q" }, ex.response.question),
      h("span", { class: "meta" }, h("span", { class: "route-pill", dataset: { route: ex.response.route } }, ex.response.route), ex.badge ? h("span", {}, ex.badge) : null));
    btn.addEventListener("click", () => { input.value = ex.response.question; show(ex, { focus: true }); });
    list.append(h("li", {}, btn));
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) { statusEl.className = "demo-status notice"; statusEl.textContent = "Type a question or choose one of the recorded examples."; return; }
    const hit = examples.find((x) => norm(x.response.question) === norm(q));
    if (hit) { show(hit, { focus: true }); return; }
    statusEl.className = "demo-status notice";
    statusEl.textContent = "This hosted page can't run new questions: it has no database or LLM. Only the recorded examples are available here. To run any question for real, start the stack locally (instructions below).";
    document.getElementById("demo-modes")?.scrollIntoView({ block: "nearest" });
  });

  walkBtn.addEventListener("click", () => {
    const n = stageNodes().length;
    setWalk(step >= n - 1 ? 0 : step + 1);
  });
  toggleBtn.addEventListener("click", () => {
    const nodes = stageNodes();
    const expand = toggleBtn.textContent === "Expand all";
    nodes.forEach((d) => { d.open = expand; d.classList.remove("current"); });
    toggleBtn.textContent = expand ? "Collapse all" : "Expand all";
    step = -1; walkBtn.textContent = "Walk through";
  });

  show(examples[0]);
  return { show, examples };
}
