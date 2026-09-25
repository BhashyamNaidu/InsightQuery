const content = document.getElementById("metrics-content");

function tile(value, label, na = false) {
  return `<div class="metric-tile ${na ? "na" : ""}"><div class="metric-value">${value}</div><div class="metric-label">${escapeHtml(label)}</div></div>`;
}

function pct(x) {
  return x === null || x === undefined ? null : `${(x * 100).toFixed(1)}%`;
}

async function loadMetrics() {
  try {
    const data = await fetchJson("/evaluations");
    render(data);
  } catch (err) {
    content.innerHTML = `<div class="error-state">Could not load evaluation results: ${escapeHtml(err.message)}</div>`;
  }
}

function render(data) {
  const { rag, intent, nl2sql, e2e } = data;

  content.innerHTML = `
    <div class="card">
      <div class="section-title">At a glance</div>
      <div class="metric-grid">
        ${intent ? tile(pct(intent.accuracy), "Intent Accuracy") : tile("—", "Intent Accuracy (not yet run)", true)}
        ${nl2sql ? tile(pct(nl2sql.malicious_questions_correctly_blocked), "Malicious SQL Blocked") : tile("—", "Malicious SQL Blocked (not yet run)", true)}
        ${rag ? tile(rag.recall_at_5, "RAG Recall@5") : tile("—", "RAG Recall@5 (not yet run)", true)}
        ${rag ? tile(rag.mrr, "RAG MRR") : tile("—", "RAG MRR (not yet run)", true)}
        ${e2e ? tile(formatMs(e2e.avg_total_latency_ms), "Avg. Investigation Latency") : tile("—", "Avg. Latency (not yet run)", true)}
      </div>
    </div>

    ${renderIntentCard(intent)}
    ${renderNl2SqlCard(nl2sql)}
    ${renderRagCard(rag)}
    ${renderE2eCard(e2e)}

    <div class="card">
      <div class="section-title">How to reproduce these numbers</div>
      <div class="sql-block">python scripts/evaluate.py</div>
      <p style="font-size:12px;color:var(--text-faint);margin-top:8px;">Runs all four evaluations against the live database and configured LLM_PROVIDER, and overwrites docs/evaluation_results.json + the per-evaluation report files this page reads from.</p>
    </div>
  `;
}

function renderIntentCard(intent) {
  if (!intent) {
    return `<div class="card"><div class="section-title">Intent Classification</div><p class="empty-state" style="padding:16px;">Not yet run. <code>python scripts/evaluate_intent.py</code></p></div>`;
  }
  const correct = intent.per_question.filter((q) => q.correct).length;
  return `
    <div class="card">
      <div class="section-title">Intent Classification</div>
      <p style="font-size:13px;color:var(--text-secondary);">${correct} / ${intent.n_questions} correct across sql/rag/hybrid/rejected categories.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Expected</th><th>Actual</th><th>Count</th></tr></thead>
          <tbody>
            ${intent.confusion_matrix.map((r) => `<tr><td>${escapeHtml(r.expected)}</td><td>${escapeHtml(r.actual)}</td><td>${r.count}</td></tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderNl2SqlCard(nl2sql) {
  if (!nl2sql) {
    return `<div class="card"><div class="section-title">NL-to-SQL</div><p class="empty-state" style="padding:16px;">Not yet run. <code>python scripts/evaluate_nl2sql.py</code></p></div>`;
  }
  return `
    <div class="card">
      <div class="section-title">NL-to-SQL Pipeline (${nl2sql.n_questions} test cases: ${nl2sql.n_legit} legitimate, ${nl2sql.n_malicious} malicious/destructive, ${nl2sql.n_unscored_edge_cases} unscored edge cases)</div>
      <div class="metric-grid">
        ${tile(pct(nl2sql.sql_generation_rate), "SQL Generation Rate")}
        ${tile(pct(nl2sql.validation_pass_rate), "Validation Pass Rate")}
        ${nl2sql.execution_success_rate !== null ? tile(pct(nl2sql.execution_success_rate), "Execution Success (of validated)") : tile("—", "Execution Success", true)}
        ${nl2sql.legit_questions_correctly_allowed !== null ? tile(pct(nl2sql.legit_questions_correctly_allowed), "Legitimate Qs Allowed") : tile("—", "Legitimate Qs Allowed", true)}
        ${nl2sql.malicious_questions_correctly_blocked !== null ? tile(pct(nl2sql.malicious_questions_correctly_blocked), "Malicious Qs Blocked") : tile("—", "Malicious Qs Blocked", true)}
      </div>
    </div>
  `;
}

function renderRagCard(rag) {
  if (!rag) {
    return `<div class="card"><div class="section-title">RAG Retrieval</div><p class="empty-state" style="padding:16px;">Not yet run. <code>python scripts/evaluate_rag.py</code></p></div>`;
  }
  return `
    <div class="card">
      <div class="section-title">RAG Retrieval (${rag.n_questions} questions, top-${rag.top_k})</div>
      <div class="metric-grid">
        ${tile(rag.recall_at_5, `Recall@${rag.top_k}`)}
        ${tile(rag.mrr, "MRR")}
      </div>
    </div>
  `;
}

function renderE2eCard(e2e) {
  if (!e2e) {
    return `<div class="card"><div class="section-title">End-to-End Latency</div><p class="empty-state" style="padding:16px;">Not yet run. <code>python scripts/evaluate_e2e.py</code></p></div>`;
  }
  const stageRows = Object.entries(e2e.avg_stage_latency_ms || {})
    .map(([stage, ms]) => `<tr><td>${escapeHtml(stage)}</td><td>${formatMs(ms)}</td></tr>`)
    .join("");
  return `
    <div class="card">
      <div class="section-title">End-to-End Latency (n=${e2e.latency_sample_size} — small sample, see docs/EVALUATION.md)</div>
      <div class="metric-grid">
        ${tile(formatMs(e2e.avg_total_latency_ms), "Avg Total")}
        ${e2e.p50_total_latency_ms !== null ? tile(formatMs(e2e.p50_total_latency_ms), "p50 Total") : tile("—", "p50 (needs ≥2 samples)", true)}
        ${e2e.p95_total_latency_ms !== null ? tile(formatMs(e2e.p95_total_latency_ms), "p95 Total") : tile("—", "p95 (needs ≥2 samples)", true)}
        ${tile(`${e2e.n_succeeded}/${e2e.n_questions}`, "Succeeded")}
      </div>
      <div class="table-wrap" style="margin-top:12px;">
        <table><thead><tr><th>Stage</th><th>Avg latency</th></tr></thead><tbody>${stageRows}</tbody></table>
      </div>
    </div>
  `;
}

loadMetrics();
