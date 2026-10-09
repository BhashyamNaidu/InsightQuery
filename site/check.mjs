// Verifies the built site: node site/check.mjs [--remote]
//  - every local href/src resolves to a file in dist; every #anchor resolves to an id
//  - every GitHub blob link and every file named in the architecture map exists in the repo tree
//  - no unreplaced {{placeholders}}, no secret-looking strings, no .env files in dist
//  - with --remote: HEAD-requests every external link and the canonical URL
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve, extname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..");
const dist = join(here, "dist");
const remote = process.argv.includes("--remote");
const errors = [];
const fail = (m) => errors.push(m);

const html = readFileSync(join(dist, "index.html"), "utf8");
const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
const BLOB = "https://github.com/BhashyamNaidu/InsightQuery/blob/master/";

const links = [...html.matchAll(/\s(?:href|src)="([^"]+)"/g)].map((m) => m[1]);
const external = new Set();
for (const l of links) {
  if (l.startsWith("#")) { if (!ids.has(l.slice(1))) fail(`broken anchor ${l}`); continue; }
  if (l.startsWith("http")) {
    external.add(l);
    if (l.startsWith(BLOB)) {
      const rel = l.slice(BLOB.length).split("#")[0];
      if (!existsSync(join(repo, rel))) fail(`GitHub link points at a path not in the repo: ${rel}`);
    }
    continue;
  }
  const p = l.split("?")[0].split("#")[0];
  if (p && !existsSync(join(dist, p))) fail(`missing local file ${p}`);
}

// files named in the architecture map (JS-generated links)
const arch = readFileSync(join(dist, "assets/js/arch.js"), "utf8");
for (const m of arch.matchAll(/files:\s*\[([^\]]*)\]/g))
  for (const f of m[1].matchAll(/"([^"]+)"/g)) if (!existsSync(join(repo, f[1]))) fail(`architecture map references missing file ${f[1]}`);

// placeholders, secrets, env files
const walk = (d, out = []) => { for (const n of readdirSync(d)) { const p = join(d, n); statSync(p).isDirectory() ? walk(p, out) : out.push(p); } return out; };
const files = walk(dist);
const secretRe = /(sk-ant-[A-Za-z0-9_-]{10,}|ANTHROPIC_API_KEY\s*=\s*\S+|postgres(ql)?:\/\/[^\s"']+:[^\s"']+@|BEGIN (RSA |EC )?PRIVATE KEY|ghp_[A-Za-z0-9]{20,})/;
for (const f of files) {
  if (/(^|[\\/])\.env/.test(f)) fail(`env file in dist: ${f}`);
  if ([".html", ".js", ".css", ".json", ".txt", ".xml", ".svg"].includes(extname(f))) {
    const t = readFileSync(f, "utf8");
    if (t.includes("{{")) fail(`unreplaced placeholder in ${f}`);
    if (secretRe.test(t)) fail(`secret-looking string in ${f}`);
  }
}

// required metadata
for (const needle of ['rel="canonical"', 'property="og:image"', 'name="twitter:card"', 'name="description"', 'property="og:title"'])
  if (!html.includes(needle)) fail(`missing metadata ${needle}`);
const og = /property="og:image" content="([^"]+)"/.exec(html)?.[1];
if (og && !og.startsWith("https://")) fail("og:image is not absolute https");
if (!existsSync(join(dist, "og-image.png"))) fail("og-image.png missing");

// recorded demo data sanity
const traces = JSON.parse(readFileSync(join(dist, "data/traces.json"), "utf8"));
for (const ex of traces.examples) if (!ex.response?.request_id || !ex.recorded_at) fail(`trace ${ex.id} lacks request_id/recorded_at`);

if (remote) {
  const siteUrl = /rel="canonical" href="([^"]+)"/.exec(html)[1];
  const targets = [...external, siteUrl, siteUrl + "og-image.png", siteUrl + "data/metrics.json"];
  for (const u of targets) {
    try {
      const r = await fetch(u, { method: "HEAD", redirect: "follow" });
      if (!r.ok) fail(`remote ${r.status} ${u}`);
    } catch (e) { fail(`remote error ${u}: ${e.message}`); }
  }
  console.log(`remote-checked ${targets.length} URLs`);
}

console.log(`checked ${links.length} links, ${files.length} files, ${traces.examples.length} recorded traces`);
if (errors.length) { console.error("\nFAILED:\n - " + errors.join("\n - ")); process.exit(1); }
console.log("OK");
