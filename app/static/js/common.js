// Shared helpers used by every dashboard page.

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Minimal, dependency-free SQL syntax highlighting: good enough for readability,
// not a real parser. Applied only to text that is already HTML-escaped.
const SQL_KEYWORDS = [
  "SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "LIMIT", "JOIN", "LEFT JOIN",
  "INNER JOIN", "ON", "AS", "AND", "OR", "NOT", "NULL", "IS", "IN", "DESC", "ASC",
  "HAVING", "WITH", "UNION", "DISTINCT", "BETWEEN", "LIKE", "CASE", "WHEN", "THEN", "ELSE", "END",
];
const SQL_FUNCTIONS = ["COUNT", "SUM", "AVG", "ROUND", "MAX", "MIN", "DATE_TRUNC", "EXTRACT", "CAST", "FILTER", "NULLIF", "STDDEV_POP", "TO_CHAR"];

function highlightSql(escapedSql) {
  let html = escapedSql;
  html = html.replace(/&#39;[^&]*?&#39;/g, (m) => `<span class="sql-string">${m}</span>`);
  const kwPattern = SQL_KEYWORDS.sort((a, b) => b.length - a.length).join("|");
  html = html.replace(new RegExp(`\\b(${kwPattern})\\b`, "gi"), '<span class="sql-keyword">$1</span>');
  const fnPattern = SQL_FUNCTIONS.join("|");
  html = html.replace(new RegExp(`\\b(${fnPattern})\\b(?=\\()`, "gi"), '<span class="sql-function">$1</span>');
  return html;
}

function formatMs(ms) {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = body && body.detail ? (body.detail.message || JSON.stringify(body.detail)) : response.statusText;
    const err = new Error(message);
    err.status = response.status;
    err.body = body;
    throw err;
  }
  return body;
}
