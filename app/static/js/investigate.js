const form = document.getElementById("query-form");
const input = document.getElementById("question-input");
const submitBtn = document.getElementById("submit-btn");
const resultArea = document.getElementById("result-area");

let currentChart = null;
let currentRows = [];
let currentPage = 0;
const PAGE_SIZE = 10;

document.querySelectorAll(".example-questions button").forEach((btn) => {
  btn.addEventListener("click", () => {
    input.value = btn.dataset.q;
    form.dispatchEvent(new Event("submit"));
  });
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;

  submitBtn.disabled = true;
  resultArea.innerHTML = `<div class="loading-state"><span class="spinner"></span>Running investigation — intent classification, SQL/retrieval, and synthesis can take a few seconds (longer on first use, or with a local LLM).</div>`;

  try {
    const data = await fetchJson("/investigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    renderResult(question, data);
  } catch (err) {
    resultArea.innerHTML = `<div class="error-state">Investigation failed: ${escapeHtml(err.message)}</div>`;
  } finally {
    submitBtn.disabled = false;
  }
});

function renderResult(question, data) {
  currentRows = (data.sql_result && data.sql_result.rows) || [];
  currentPage = 0;

  const routeLabel = { sql: "SQL Analysis", rag: "Document Lookup", hybrid: "Analytical + Contextual", rejected: "Rejected — Out of Scope" }[data.route] || data.route;

  resultArea.innerHTML = `
    <div class="card">
      <div class="section-title">Intent</div>
      <span class="badge badge-route">${escapeHtml(routeLabel)}</span>
      ${data.intent_reasoning ? `<p style="margin-top:8px;color:var(--text-secondary);font-size:13px;">${escapeHtml(data.intent_reasoning)}</p>` : ""}
    </div>

    ${renderSqlSection(data.sql_result)}
    ${renderAnswerSection(data.synthesis)}
    ${renderChartAndTableSection(data.sql_result)}
    ${renderEvidenceSection(data.evidence)}
    ${renderTraceSection(data)}
    ${renderTrustSection(data)}
  `;

  const rowsForChart = currentRows;
  if (rowsForChart.length > 0) {
    renderChart(rowsForChart);
  }
  renderTablePage(); // binds its own pagination button listeners on each render
}

function renderSqlSection(sqlResult) {
  if (!sqlResult) return "";
  const sql = sqlResult.executed_sql || sqlResult.generated_sql;
  const validationBadges = sqlResult.validation_ok
    ? `<span class="badge badge-success">&#10003; Validated</span> <span class="badge badge-success">&#10003; Read-only</span>`
    : `<span class="badge badge-danger">&#10007; Rejected</span>`;

  return `
    <div class="card">
      <div class="section-title">Generated SQL</div>
      ${sql ? `<div class="sql-block">${highlightSql(escapeHtml(sql))}</div>` : `<p style="color:var(--text-faint);font-size:13px;">No SQL generated for this question.</p>`}
      <div style="margin-top:10px;">${validationBadges}</div>
      ${!sqlResult.validation_ok && sqlResult.rejection_reason ? `<p style="margin-top:8px;font-size:13px;color:var(--danger);">${escapeHtml(sqlResult.rejection_reason)}</p>` : ""}
      ${sqlResult.validation_ok ? `<p style="margin-top:8px;font-size:12px;color:var(--text-faint);">${sqlResult.row_count} row(s) returned</p>` : ""}
    </div>
  `;
}

function renderAnswerSection(synthesis) {
  if (!synthesis) {
    return `<div class="card"><div class="section-title">Synthesized Answer</div><p style="color:var(--text-faint);font-size:13px;">No synthesis available (LLM unavailable, or the question was rejected before synthesis). The deterministic results above/below are unaffected.</p></div>`;
  }
  const confBadgeClass = { high: "badge-success", medium: "badge-warning", low: "badge-danger" }[synthesis.confidence] || "badge-neutral";
  return `
    <div class="card">
      <div class="section-title">Synthesized Answer</div>
      <span class="badge ${confBadgeClass}">${escapeHtml(synthesis.confidence)} confidence</span>
      <p class="answer-text" style="margin-top:12px;">${escapeHtml(synthesis.answer)}</p>
      ${synthesis.citations.length ? `<div style="margin-top:10px;">${synthesis.citations.map((c) => `<span class="citation-tag">${escapeHtml(c)}</span>`).join("")}</div>` : ""}
      ${synthesis.limitations.length ? `<div style="margin-top:12px;"><div class="section-title" style="margin-bottom:6px;">Limitations</div><ul class="limitations-list">${synthesis.limitations.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul></div>` : ""}
    </div>
  `;
}

function renderChartAndTableSection(sqlResult) {
  const rows = (sqlResult && sqlResult.rows) || [];
  if (rows.length === 0) return "";
  return `
    <div class="card">
      <div class="section-title">Visual Analysis</div>
      <canvas id="result-chart"></canvas>
    </div>
    <div class="card">
      <div class="section-title">Data (${rows.length} row${rows.length === 1 ? "" : "s"})</div>
      <div class="table-wrap" id="table-wrap"></div>
      <div class="pagination" id="pagination-controls"></div>
    </div>
  `;
}

function renderTablePage() {
  const wrap = document.getElementById("table-wrap");
  if (!wrap || currentRows.length === 0) return;

  const columns = Object.keys(currentRows[0]);
  const start = currentPage * PAGE_SIZE;
  const pageRows = currentRows.slice(start, start + PAGE_SIZE);

  wrap.innerHTML = `
    <table>
      <thead><tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>
      <tbody>
        ${pageRows.map((row) => `<tr>${columns.map((c) => `<td>${escapeHtml(row[c])}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;

  const totalPages = Math.ceil(currentRows.length / PAGE_SIZE);
  const controls = document.getElementById("pagination-controls");
  if (controls) {
    controls.innerHTML = `
      <button class="page-btn" data-dir="-1" ${currentPage === 0 ? "disabled" : ""}>&larr; Prev</button>
      <span>Page ${currentPage + 1} of ${totalPages}</span>
      <button class="page-btn" data-dir="1" ${currentPage >= totalPages - 1 ? "disabled" : ""}>Next &rarr;</button>
    `;
    controls.querySelectorAll(".page-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        currentPage += parseInt(btn.dataset.dir, 10);
        renderTablePage();
      });
    });
  }
}

function renderEvidenceSection(evidence) {
  if (!evidence || evidence.length === 0) return "";
  return `
    <div class="card">
      <div class="section-title">Evidence (${evidence.length} document chunk${evidence.length === 1 ? "" : "s"})</div>
      ${evidence
        .map(
          (e) => `
        <div class="evidence-item">
          <div class="evidence-title">${escapeHtml(e.document_title)}</div>
          <div class="evidence-meta">${escapeHtml(e.document_source)} &middot; similarity ${e.similarity.toFixed(3)}</div>
          <div class="evidence-excerpt">${escapeHtml(e.content.slice(0, 280))}${e.content.length > 280 ? "…" : ""}</div>
        </div>`
        )
        .join("")}
    </div>
  `;
}

function renderTraceSection(data) {
  const stages = [
    { key: "intent", label: "Intent Classification" },
    { key: "sql", label: "SQL Generation + Validation" },
    { key: "rag", label: "RAG Retrieval" },
    { key: "synthesis", label: "LLM Synthesis" },
  ];
  const stageMs = data.stage_latency_ms || {};

  return `
    <div class="card">
      <div class="section-title">System Trace</div>
      <div class="trace">
        ${stages
          .map((s, i) => {
            const ran = Object.prototype.hasOwnProperty.call(stageMs, s.key);
            return `
              ${i > 0 ? '<span class="trace-arrow">&rarr;</span>' : ""}
              <div class="trace-step ${ran ? "" : "skipped"}">
                <div class="step-name">${s.label}</div>
                <div class="step-time">${ran ? formatMs(stageMs[s.key]) : "skipped"}</div>
              </div>`;
          })
          .join("")}
      </div>
      <p style="margin-top:10px;font-size:12px;color:var(--text-faint);">Total latency: ${formatMs(data.latency_ms)} &middot; request ${escapeHtml(data.request_id)}</p>
    </div>
  `;
}

function renderTrustSection(data) {
  const sqlSafe = data.sql_result ? data.sql_result.validation_ok : null;
  const hasEvidence = (data.evidence && data.evidence.length > 0) || (data.sql_result && data.sql_result.validation_ok);
  const evidenceBacked = data.synthesis && (data.synthesis.citations.length > 0 || (data.sql_result && data.sql_result.row_count > 0));

  const items = [
    {
      ok: sqlSafe === null ? null : sqlSafe,
      label: "Read-only, validated SQL",
      title: "The generated SQL passed app/nlsql/validator.py's AST-level checks and ran over a database role with SELECT-only grants.",
    },
    {
      ok: hasEvidence,
      label: "Evidence available",
      title: "At least one SQL result row or retrieved document chunk was found to ground the answer.",
    },
    {
      ok: !!data.synthesis,
      label: "Synthesis produced",
      title: "The LLM produced a schema-validated JSON answer. If false, the LLM was unavailable or its output failed validation twice.",
    },
    {
      ok: !!evidenceBacked,
      label: "Answer is evidence-backed",
      title: "The synthesized answer cites a retrieved document or is grounded in returned SQL rows, not general LLM knowledge.",
    },
  ];

  return `
    <div class="card">
      <div class="section-title">Security &amp; Trust</div>
      <div class="trust-grid">
        ${items
          .map(
            (it) => `
          <div class="trust-item">
            <span class="${it.ok === null ? "" : it.ok ? "icon-ok" : "icon-no"}">${it.ok === null ? "—" : it.ok ? "&#10003;" : "&#10007;"}</span>
            ${escapeHtml(it.label)}
          </div>`
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderChart(rows) {
  const canvas = document.getElementById("result-chart");
  if (!canvas) return;

  const columns = Object.keys(rows[0]);
  const numericCols = columns.filter((c) => rows.every((r) => r[c] === null || !isNaN(parseFloat(r[c]))));
  const labelCol = columns.find((c) => !numericCols.includes(c)) || columns[0];
  const valueCol = numericCols.find((c) => c !== labelCol);

  if (!valueCol || rows.length < 2) return; // not enough shape for a meaningful chart

  const isTimeSeries = /month|date|year|week/i.test(labelCol);
  const tooManyCategories = rows.length > 25;
  if (tooManyCategories && !isTimeSeries) return;

  const labels = rows.map((r) => String(r[labelCol]));
  const values = rows.map((r) => parseFloat(r[valueCol]) || 0);

  if (currentChart) currentChart.destroy();
  currentChart = new Chart(canvas, {
    type: isTimeSeries ? "line" : "bar",
    data: {
      labels,
      datasets: [
        {
          label: valueCol,
          data: values,
          backgroundColor: "#2352c9",
          borderColor: "#2352c9",
          tension: 0.25,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } },
    },
  });
}
