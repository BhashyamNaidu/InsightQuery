// Interactive architecture map. Every node mirrors a real module in the repository; the file links
// are checked against the tree by site/check.mjs at build time so the map cannot silently drift.

import { h, clear } from "./util.js";
import { initTabs } from "./tabs.js";

export const REPO = "https://github.com/BhashyamNaidu/InsightQuery/blob/master/";

export const NODES = {
  client: {
    title: "Dashboard / API client", sub: "browser or HTTP", role: "Entry point",
    does: "Sends a question to the API and renders the whole trace — route, SQL, verdict, rows, sources, answer, timings — not just a chat bubble.",
    inputs: "A natural-language question (max 2,000 characters).", outputs: "The structured investigation response.",
    tech: "Jinja2 templates, vanilla JavaScript, Chart.js", fail: "If the API is down the dashboard shows an error state; no partial result is invented.",
    sec: "The dashboard escapes model output before display.",
    files: ["app/templates/index.html", "app/static/js/investigate.js"],
  },
  api: {
    title: "FastAPI orchestration", sub: "POST /investigate", role: "Coordinator",
    does: "Validates the request, runs the stages in order, times each one, and always writes an audit record — even when a stage fails.",
    inputs: "InvestigateRequest.", outputs: "InvestigateResponse (route, SQL result, evidence, synthesis, per-stage latency).",
    tech: "FastAPI, Pydantic v2", fail: "Dependency failures become structured 502 errors with a code (e.g. llm_call_failed); a failed LLM stage degrades the result instead of crashing the request.",
    sec: "Errors never include stack traces or configuration.",
    files: ["app/api/routes.py", "app/services/investigation.py", "app/schemas/investigation.py"],
  },
  intent: {
    title: "Intent classifier", sub: "sql · rag · hybrid · rejected", role: "LLM, constrained",
    does: "A model call that picks the route. Its output is a constrained JSON value, parsed defensively.",
    inputs: "The question.", outputs: "A route and a one-line reasoning.",
    tech: "LLM provider interface, strict JSON parsing", fail: "Unparseable output defaults to hybrid. Measured accuracy is 16/20 on the local model, so routing is a known weak point.",
    sec: "A wrong route cannot cause an unsafe query: SQL still has to pass the validator.",
    files: ["app/services/intent.py", "app/llm/json_utils.py"],
  },
  nl2sql: {
    title: "SQL generator", sub: "LLM proposes SQL", role: "LLM, untrusted",
    does: "Writes a single SELECT from the question and the schema of four allowed tables.",
    inputs: "Question + schema description.", outputs: "Candidate SQL (untrusted text).",
    tech: "Prompted LLM call", fail: "May produce a query that validates but is semantically wrong (e.g. filtering on the wrong column). Execution success is not correctness.",
    sec: "Its output is never executed directly.",
    files: ["app/nlsql/generator.py", "app/nlsql/schema.py", "app/llm/prompts.py"],
  },
  validator: {
    title: "AST validator", sub: "deterministic gate", role: "Safety boundary",
    does: "Parses SQL into a syntax tree and enforces: one SELECT, allow-listed tables and columns, no comments, a function deny-list, an enforced LIMIT.",
    inputs: "Candidate SQL.", outputs: "Accepted (possibly with LIMIT added) or rejected with a specific reason.",
    tech: "sqlglot", fail: "Must never raise: a crash on non-string input was found and fixed. Column checks are table-agnostic (documented).",
    sec: "A rejection is final — it is logged, never executed, never sent back for rewriting, and never narrated as an empty result.",
    files: ["app/nlsql/validator.py", "tests/test_sql_validator.py"],
  },
  executor: {
    title: "Read-only executor", sub: "least-privilege role", role: "Safety boundary",
    does: "Runs validated SQL as insightquery_readonly with a statement timeout, passing the text to PostgreSQL unmodified.",
    inputs: "Validated SQL.", outputs: "Rows.",
    tech: "SQLAlchemy exec_driver_sql, psycopg 3", fail: "Driver-level parameter parsing once broke literal % and : in SQL; fixed and covered by real-database tests.",
    sec: "SELECT is granted on exactly four tables. Even a validator bug could not write or read internal tables.",
    files: ["app/nlsql/executor.py", "scripts/init_db_roles.sql", "scripts/grant_readonly.sql"],
  },
  repair: {
    title: "Bounded repair", sub: "on a PG error: one retry, re-validated", role: "LLM, untrusted",
    does: "If PostgreSQL rejects an already-validated query, the model gets one chance to fix it, shown its SQL and a truncated error.",
    inputs: "Failed SQL + database error (300 chars).", outputs: "A second candidate, which re-enters the validator.",
    tech: "pipeline.py control flow", fail: "Measured benefit is not demonstrated (within run-to-run noise).",
    sec: "Re-validated in full; validator rejections and infrastructure errors are never repaired; no loop. The error text is a small prompt-injection channel, documented.",
    files: ["app/nlsql/pipeline.py", "tests/test_sql_pipeline.py"],
  },
  pg: {
    title: "PostgreSQL analytics tables", sub: "crimes + 3 dimensions", role: "Source of truth",
    does: "Holds 263,841 incident records for 2023 in a star schema. All numbers in an answer originate here.",
    inputs: "Read-only SELECTs.", outputs: "Rows.",
    tech: "PostgreSQL 16, Alembic migrations", fail: "Data is preliminary and block-level by design; single year only.",
    sec: "Only these four tables are reachable by generated SQL.",
    files: ["alembic/versions/0001_initial_schema.py", "scripts/ingest_data.py"],
  },
  docs: {
    title: "Document corpus", sub: "15 curated documents", role: "Source of truth",
    does: "Original reference notes on classification codes, data-quality caveats and interpretation pitfalls.",
    inputs: "Markdown files.", outputs: "Text for chunking.",
    tech: "data/documents/", fail: "Small corpus: retrieval quality here does not generalize to arbitrary collections.",
    sec: "Authored for this project, so there is no third-party content path; the synthesis prompt still treats it as data.",
    files: ["data/documents/manifest.json", "scripts/ingest_documents.py"],
  },
  chunk: {
    title: "Chunking", sub: "ingest time", role: "Offline",
    does: "Splits each document into overlapping word-count chunks (an approximation of token counts).",
    inputs: "Documents.", outputs: "30 chunks.",
    tech: "Python", fail: "Word-count based, not tokenizer-exact.",
    sec: "—", files: ["app/rag/chunking.py", "tests/test_chunking.py"],
  },
  embed: {
    title: "Embeddings", sub: "all-MiniLM-L6-v2 · 384-d", role: "Local model",
    does: "Turns chunks (at ingest) and questions (at query time) into vectors locally — no API call.",
    inputs: "Text.", outputs: "Normalized 384-dimensional vectors.",
    tech: "sentence-transformers (CPU)", fail: "First call in a fresh process pays a one-time model load (~30–45 s observed).",
    sec: "Nothing is sent to a third party.", files: ["app/rag/embeddings.py"],
  },
  retrieve: {
    title: "pgvector retrieval", sub: "cosine top-k", role: "Deterministic",
    does: "Finds the nearest chunks by cosine distance with an exact scan. No ANN index: at this size an index hurt recall, so it was removed.",
    inputs: "Question vector.", outputs: "Top-5 passages with titles and similarity.",
    tech: "pgvector, SQLAlchemy", fail: "Measured Recall@5 = 1.00 and MRR = 0.956 on 15 questions — a small set.",
    sec: "Read path only; retrieved text is later treated as data, not instructions.",
    files: ["app/rag/retrieval.py", "docs/RAG_EVALUATION.md"],
  },
  synth: {
    title: "Evidence-grounded synthesis", sub: "LLM + citation check", role: "LLM, untrusted",
    does: "Explains the SQL rows and retrieved passages, returning a schema-validated JSON answer with citations, confidence and limitations.",
    inputs: "Question, SQL rows, retrieved passages.", outputs: "Answer, citations, confidence, limitations.",
    tech: "Provider interface (Ollama default, Anthropic optional), Pydantic", fail: "Can drift from the evidence or explain it wrongly (seen in recorded runs); its confidence is self-reported. It is never handed a rejected or failed SQL branch as if it were an empty result . When a hybrid question has no database result it once answered the database half from general knowledge (5 of 5 probe runs, confidence high or medium); with the system notice and the code-enforced qualification below, 0 of 5 did. That is a small sample, and free prose can never be fully verified by code.",
    sec: "A validator rejection ends the SQL branch: the SQL is not executed, and with no documents the system returns fixed text saying the request was blocked, with no LLM call. In hybrid questions the model sees only the retrieved documents plus a system notice that the database part is unanswered; then code, not the model, puts a fixed lead-in sentence in front of the answer, caps confidence at LOW, and records the gap as a limitation. Each citation is compared with the documents actually retrieved; non-matching ones are dropped and noted. That closes one reproduced injection vector, not injection in general.",
    files: ["app/llm/synthesis.py", "app/llm/client.py", "tests/test_synthesis.py"],
  },
  response: {
    title: "Response", sub: "InvestigateResponse", role: "Output",
    does: "Returns the trace as separate fields so a reader can tell dataset facts from derived analytics, retrieved context and LLM explanation.",
    inputs: "All stage outputs.", outputs: "JSON.", tech: "Pydantic", fail: "—", sec: "Structured errors only.",
    files: ["app/schemas/investigation.py"],
  },
  audit: {
    title: "Audit log", sub: "query_log table", role: "Observability",
    does: "Stores each run: question, route, original SQL, any repaired SQL and the database error, validation verdict, row count, per-stage latency, model and token counts.",
    inputs: "Every stage's output.", outputs: "A row per run, retrievable via /evidence/{id} and shown in History.",
    tech: "PostgreSQL, Alembic 0004", fail: "Records are written even for failures and rejections.",
    sec: "Not readable by the generated-SQL role (explicit grants).",
    files: ["app/models/query_log.py", "alembic/versions/0004_query_log_sql_repair_audit.py"],
  },
};

const VIEWS = {
  all: { caption: "The full request path. SQL and document retrieval run in separate lanes; only the LLM nodes (amber edge) are non-deterministic, and each is followed by a deterministic check.", on: Object.keys(NODES) },
  sql: { caption: "The SQL safety path: model output is untrusted at every hop. The validator and the database role are independent — either alone would stop a destructive statement.", on: ["api", "intent", "nl2sql", "validator", "executor", "repair", "pg", "response", "audit"] },
  rag: { caption: "The RAG path: documents are chunked and embedded offline; at query time the question is embedded locally and compared in pgvector. Retrieved passages are evidence, and the citation check keeps the answer tied to them.", on: ["api", "intent", "docs", "chunk", "embed", "retrieve", "synth", "response"] },
  audit: { caption: "Where the audit trail comes from: every stage reports into one query_log row, including the original SQL, the database error and any repair — so a surprising answer can be traced afterwards.", on: ["api", "intent", "nl2sql", "validator", "executor", "repair", "retrieve", "synth", "audit"] },
};

const arrow = () => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 16 16"); s.setAttribute("aria-hidden", "true");
  s.innerHTML = '<path d="M8 2v11M3.5 9 8 13.5 12.5 9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>';
  return h("div", { class: "arch-arrow" }, s);
};

const KIND = { pg: "store", docs: "store", validator: "gate", executor: "gate", nl2sql: "llm", intent: "llm", repair: "llm", synth: "llm", audit: "audit" };

export function initArchitecture() {
  const map = document.getElementById("arch-map");
  const detail = document.getElementById("arch-detail");
  const caption = document.getElementById("arch-caption");
  const nodeEls = {};

  const node = (id) => {
    const n = NODES[id];
    const b = h("button", { class: "node", type: "button", "aria-pressed": "false", dataset: { id, kind: KIND[id] || "" } },
      h("span", { class: "t" }, n.title), h("span", { class: "s" }, n.sub));
    b.addEventListener("click", () => select(id));
    nodeEls[id] = b;
    return b;
  };
  const lane = (key, label, ids) => {
    const el = h("div", { class: "arch-lane", dataset: { lane: key } }, h("h3", {}, label));
    ids.forEach((id, i) => { if (i) el.append(arrow()); el.append(node(id)); });
    return el;
  };

  clear(map);
  map.append(node("client"), arrow(), node("api"), arrow(), node("intent"), arrow(),
    h("div", { class: "arch-row", style: "--cols:2" },
      lane("sql", "SQL path", ["nl2sql", "validator", "executor", "pg", "repair"]),
      lane("rag", "RAG path", ["docs", "chunk", "embed", "retrieve"])),
    arrow(), node("synth"), arrow(),
    h("div", { class: "arch-row", style: "--cols:2" }, node("response"), node("audit")));

  function select(id) {
    const n = NODES[id];
    Object.entries(nodeEls).forEach(([k, el]) => el.setAttribute("aria-pressed", String(k === id)));
    clear(detail);
    detail.append(
      h("p", { class: "role" }, n.role),
      h("h3", {}, n.title),
      h("dl", {},
        h("dt", {}, "Responsibility"), h("dd", {}, n.does),
        h("dt", {}, "Inputs → outputs"), h("dd", {}, `${n.inputs} → ${n.outputs}`),
        h("dt", {}, "Technology"), h("dd", {}, n.tech),
        h("dt", {}, "Failure modes"), h("dd", {}, n.fail),
        h("dt", {}, "Security"), h("dd", { class: "sec" }, n.sec),
        h("dt", {}, "Source"), h("dd", {}, h("ul", {}, n.files.map((f) => h("li", {}, h("a", { href: REPO + f, rel: "noopener" }, f)))))));
  }

  function applyView(view) {
    const v = VIEWS[view];
    caption.textContent = v.caption;
    const dim = view !== "all";
    map.classList.toggle("dim", dim);
    Object.entries(nodeEls).forEach(([id, el]) => el.classList.toggle("hl", v.on.includes(id)));
    map.querySelectorAll(".arch-lane").forEach((l) => l.classList.toggle("hl", [...l.querySelectorAll(".node")].some((n) => n.classList.contains("hl"))));
  }

  initTabs(document.getElementById("arch-tabs"), (tab) => applyView(tab.dataset.view));
  select("validator");
}
