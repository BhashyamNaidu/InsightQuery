const content = document.getElementById("history-content");

async function loadHistory() {
  try {
    const data = await fetchJson("/investigations?limit=50");
    renderHistory(data.results);
  } catch (err) {
    content.innerHTML = `<div class="error-state">Could not load history: ${escapeHtml(err.message)}</div>`;
  }
}

function renderHistory(results) {
  if (!results || results.length === 0) {
    content.innerHTML = `<div class="empty-state">No investigations logged yet. Run one from the <a href="/">Investigate</a> page.</div>`;
    return;
  }

  const routeBadge = (route) => {
    const cls = { sql: "badge-route", rag: "badge-route", hybrid: "badge-route", rejected: "badge-neutral" }[route] || "badge-neutral";
    return `<span class="badge ${cls}">${escapeHtml(route)}</span>`;
  };

  content.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Question</th>
            <th>Route</th>
            <th>SQL Safe</th>
            <th>Rows</th>
            <th>Latency</th>
            <th>Provider</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          ${results
            .map(
              (r) => `
            <tr class="history-row" data-id="${escapeHtml(r.id)}">
              <td>${escapeHtml(r.question.slice(0, 80))}${r.question.length > 80 ? "…" : ""}</td>
              <td>${routeBadge(r.route)}</td>
              <td>${r.sql_validation_ok === null ? "—" : r.sql_validation_ok ? '<span class="icon-ok">&#10003;</span>' : '<span class="icon-no">&#10007;</span>'}</td>
              <td>${r.row_count === null ? "—" : r.row_count}</td>
              <td>${formatMs(r.latency_ms)}</td>
              <td>${escapeHtml(r.llm_provider || "—")}</td>
              <td>${r.created_at ? new Date(r.created_at).toLocaleString() : "—"}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>
    <div id="detail-panel"></div>
  `;

  document.querySelectorAll(".history-row").forEach((row) => {
    row.addEventListener("click", () => loadDetail(row.dataset.id));
  });
}

async function loadDetail(id) {
  const panel = document.getElementById("detail-panel");
  panel.innerHTML = `<div class="loading-state"><span class="spinner"></span>Loading detail…</div>`;
  try {
    const detail = await fetchJson(`/evidence/${id}`);
    panel.innerHTML = `
      <div class="card" style="margin-top:16px;">
        <div class="section-title">Detail — ${escapeHtml(detail.request_id)}</div>
        <p style="font-size:14px;"><strong>Question:</strong> ${escapeHtml(detail.question)}</p>
        ${detail.generated_sql ? `<div class="sql-block">${highlightSql(escapeHtml(detail.generated_sql))}</div>` : ""}
        ${detail.sql_rejection_reason ? `<p style="color:var(--danger);font-size:13px;">${escapeHtml(detail.sql_rejection_reason)}</p>` : ""}
        <table style="margin-top:12px;">
          <tbody>
            <tr><td>Route</td><td>${escapeHtml(detail.route)}</td></tr>
            <tr><td>Total latency</td><td>${formatMs(detail.latency_ms)}</td></tr>
            <tr><td>Intent stage</td><td>${formatMs(detail.stage_latency_ms.intent)}</td></tr>
            <tr><td>SQL stage</td><td>${formatMs(detail.stage_latency_ms.sql)}</td></tr>
            <tr><td>RAG stage</td><td>${formatMs(detail.stage_latency_ms.rag)}</td></tr>
            <tr><td>Synthesis stage</td><td>${formatMs(detail.stage_latency_ms.synthesis)}</td></tr>
            <tr><td>LLM provider / model</td><td>${escapeHtml(detail.llm_provider || "—")} / ${escapeHtml(detail.llm_model || "—")}</td></tr>
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    panel.innerHTML = `<div class="error-state">Could not load detail: ${escapeHtml(err.message)}</div>`;
  }
}

loadHistory();
