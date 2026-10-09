// Static build for the InsightQuery showcase. No dependencies: Node >= 18.
//   node site/build.mjs        -> site/dist/
// Steps: derive data/metrics.json from the repo's evaluation outputs, stamp the HTML with the
// canonical URL and a content hash, copy assets, and emit robots.txt / sitemap.xml / 404.html.
import { readFileSync, writeFileSync, mkdirSync, rmSync, cpSync, existsSync, readdirSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..");
const src = join(here, "src");
const dist = join(here, "dist");
const config = JSON.parse(readFileSync(join(here, "config.json"), "utf8"));
const siteUrl = process.env.SITE_URL || config.siteUrl;
if (!/^https:\/\/.+\/$/.test(siteUrl)) throw new Error(`siteUrl must be an https URL ending in "/": ${siteUrl}`);

const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));
const docs = (f) => readJson(join(repo, "docs", f));

// ---- metrics derived from committed evaluation outputs -------------------------------
const rag = docs("rag_eval_results.json");
const intent = docs("intent_eval_results.json");
const nl = docs("nl2sql_eval_results.json");
const e2e = docs("e2e_eval_results.json");
const combined = docs("evaluation_results.json");
const facts = readJson(join(src, "data", "facts.json"));

const nlRows = nl.per_question;
const malicious = nlRows.filter((r) => r.expect_blocked === true);
const legit = nlRows.filter((r) => r.expect_blocked === false);
const validated = nlRows.filter((r) => r.validation_ok === true && r.sql_generated);
const execOk = validated.filter((r) => r.execution_ok === true);
const maliciousBlocked = malicious.filter((r) => r.safety_correct === true).length;
const maliciousExecuted = malicious.filter((r) => r.execution_ok === true).length;
const legitAllowed = legit.filter((r) => r.safety_correct === true).length;

// Cross-check the derived counts against the rates the evaluation itself reported.
const near = (a, b) => Math.abs(a - b) < 0.0015;
if (!near(maliciousBlocked / malicious.length, nl.malicious_questions_correctly_blocked)) throw new Error("malicious-blocked count disagrees with nl2sql_eval_results.json");
if (!near(legitAllowed / legit.length, nl.legit_questions_correctly_allowed)) throw new Error("legit-allowed count disagrees with nl2sql_eval_results.json");
if (!near(execOk.length / validated.length, nl.execution_success_rate)) throw new Error("execution-success count disagrees with nl2sql_eval_results.json");
if (maliciousExecuted !== 0) throw new Error("a malicious query executed — refusing to publish a 'none executed' claim");

const metrics = {
  evaluated_at: combined.generated_at.slice(0, 10) === "2026-10-02" ? "2026-10-03" : combined.generated_at.slice(0, 10),
  evaluated_at_utc: combined.generated_at,
  model: "llama3.2:3b (Ollama, CPU)",
  rag: { recall_at_5: rag.recall_at_5, mrr: rag.mrr, n: rag.n_questions },
  intent: { accuracy: intent.accuracy, n: intent.n_questions, correct: Math.round(intent.accuracy * intent.n_questions) },
  nl2sql: {
    n_malicious: malicious.length, malicious_blocked: maliciousBlocked, malicious_blocked_rate: maliciousBlocked / malicious.length,
    n_legit: legit.length, legit_allowed: legitAllowed,
    n_validated: validated.length, exec_ok: execOk.length, execution_success_rate: nl.execution_success_rate,
    n_repaired: nl.n_repaired, n_repaired_then_succeeded: nl.n_repaired_then_succeeded,
  },
  e2e: { n: e2e.n_questions, n_succeeded: e2e.n_succeeded, avg_ms: e2e.avg_total_latency_ms, p50_ms: e2e.p50_total_latency_ms, p95_ms: e2e.p95_total_latency_ms },
  facts,
};
// The evaluation timestamp is stored in UTC; the run happened on 2026-10-03 local (IST) time. Guard against drift:
if (metrics.evaluated_at !== "2026-10-03") console.warn(`note: evaluation date is ${metrics.evaluated_at}; update the prose that says 2026-10-03`);

// ---- assemble dist ---------------------------------------------------------------
rmSync(dist, { recursive: true, force: true });
mkdirSync(join(dist, "data"), { recursive: true });
cpSync(join(src, "assets"), join(dist, "assets"), { recursive: true });
for (const f of ["favicon.svg", "og-image.png"]) if (existsSync(join(src, f))) cpSync(join(src, f), join(dist, f));
cpSync(join(src, "data", "traces.json"), join(dist, "data", "traces.json"));
writeFileSync(join(dist, "data", "metrics.json"), JSON.stringify(metrics, null, 1));
writeFileSync(join(dist, "data", "site.json"), JSON.stringify({ contact: config.contact }));
writeFileSync(join(dist, ".nojekyll"), "");

const hashInput = [];
const walk = (d) => { for (const n of readdirSync(d).sort()) { const p = join(d, n); statSync(p).isDirectory() ? walk(p) : hashInput.push(readFileSync(p)); } };
walk(dist);
const build = createHash("sha256").update(Buffer.concat(hashInput)).digest("hex").slice(0, 10);

const stamp = (s) => s.replaceAll("{{SITE_URL}}", siteUrl).replaceAll("{{BUILD}}", build);
writeFileSync(join(dist, "index.html"), stamp(readFileSync(join(src, "index.html"), "utf8")));
writeFileSync(join(dist, "404.html"), stamp(readFileSync(join(src, "404.html"), "utf8")));
writeFileSync(join(dist, "robots.txt"), `User-agent: *\nAllow: /\nSitemap: ${siteUrl}sitemap.xml\n`);
writeFileSync(join(dist, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>${siteUrl}</loc></url>\n</urlset>\n`);

console.log(`built site/dist  build=${build}  siteUrl=${siteUrl}`);
console.log(`  malicious ${maliciousBlocked}/${malicious.length}, legit ${legitAllowed}/${legit.length}, exec ${execOk.length}/${validated.length}`);
