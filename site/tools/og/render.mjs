// Renders the social preview (src/og-image.png) from og.html with headless Edge/Chrome.
// Fonts are inlined as data URIs so the screenshot never races a font download.
import { readFileSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { tmpdir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const site = resolve(here, "..", "..");
const b64 = (f) => readFileSync(join(site, "src/assets/fonts", f)).toString("base64");
let html = readFileSync(join(here, "og.html"), "utf8")
  .replace('url("../../src/assets/fonts/inter-latin.woff2")', `url(data:font/woff2;base64,${b64("inter-latin.woff2")})`)
  .replace('url("../../src/assets/fonts/jetbrains-mono-latin.woff2")', `url(data:font/woff2;base64,${b64("jetbrains-mono-latin.woff2")})`);
const tmp = join(tmpdir(), "iq-og.html");
writeFileSync(tmp, html);
const browsers = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
].filter(existsSync);
if (!browsers.length) throw new Error("No Edge/Chrome found for headless rendering");
const out = join(site, "src/og-image.png");
rmSync(out, { force: true });
execFileSync(browsers[0], ["--headless", "--disable-gpu", "--hide-scrollbars", `--user-data-dir=${join(tmpdir(), "iq-og-profile")}`, "--window-size=1200,630", `--screenshot=${out}`, pathToFileURL(tmp).href], { stdio: "inherit" });
// The browser launcher can exit before the screenshot is flushed; wait for the file.
const t0 = Date.now();
while (!existsSync(out) && Date.now() - t0 < 30000) await new Promise((r) => setTimeout(r, 250));
await new Promise((r) => setTimeout(r, 500));
if (!existsSync(out)) throw new Error("screenshot was not written");
console.log("wrote", out);
