import { loadJson, h, clear } from "./util.js";
import { initTabs } from "./tabs.js";
import { initArchitecture } from "./arch.js";
import { initDemo } from "./demo.js";
import { renderHero } from "./hero.js";
import { renderMetrics } from "./metrics.js";

const $ = (s, r = document) => r.querySelector(s);

/* ---- theme ---- */
const root = document.documentElement;
$("#theme-toggle")?.addEventListener("click", () => {
  const next = root.dataset.theme === "light" ? "dark" : "light";
  root.dataset.theme = next;
  $('meta[name="theme-color"]')?.setAttribute("content", next === "light" ? "#f5f7fb" : "#060a13");
  try { localStorage.setItem("iq-theme", next); } catch (e) { /* storage may be blocked; theme still applies for this visit */ }
});
if (root.dataset.theme === "light") $('meta[name="theme-color"]')?.setAttribute("content", "#f5f7fb");

/* ---- mobile nav ---- */
const navBtn = $("#nav-toggle"), nav = $("#primary-nav");
navBtn?.addEventListener("click", () => {
  const open = nav.classList.toggle("open");
  navBtn.setAttribute("aria-expanded", String(open));
});
nav?.addEventListener("click", (e) => { if (e.target.closest("a")) { nav.classList.remove("open"); navBtn?.setAttribute("aria-expanded", "false"); } });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && nav?.classList.contains("open")) { nav.classList.remove("open"); navBtn?.setAttribute("aria-expanded", "false"); navBtn?.focus(); } });

/* ---- scroll spy ---- */
const links = [...document.querySelectorAll(".primary-nav a")];
const targets = links.map((a) => document.getElementById(a.getAttribute("href").slice(1))).filter(Boolean);
if ("IntersectionObserver" in window && targets.length) {
  const spy = new IntersectionObserver((entries) => {
    for (const en of entries) if (en.isIntersecting) {
      links.forEach((a) => a.removeAttribute("aria-current"));
      links.find((a) => a.getAttribute("href") === `#${en.target.id}`)?.setAttribute("aria-current", "true");
    }
  }, { rootMargin: "-45% 0px -50% 0px" });
  targets.forEach((t) => spy.observe(t));
}

/* ---- reveal on scroll (content is visible by default; this only adds motion) ---- */
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
if (!reduce && "IntersectionObserver" in window) {
  const io = new IntersectionObserver((entries) => entries.forEach((en) => {
    if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
  }), { rootMargin: "0px 0px -8% 0px" });
  document.querySelectorAll(".section-head, .lane, .card, .metric, .qa, .layers, .ladder").forEach((el) => { el.classList.add("reveal"); io.observe(el); });
  // Safety net: never leave content hidden if the observer does not fire (e.g. print, bots, very tall viewports).
  setTimeout(() => document.querySelectorAll(".reveal:not(.in)").forEach((el) => el.classList.add("in")), 2500);
}

/* ---- static tabs (security case studies) ---- */
document.querySelectorAll("[data-tabs]").forEach((el) => { if (el.id !== "arch-tabs") initTabs(el); });
initArchitecture();

/* ---- share / copy link ---- */
const canonical = $('link[rel="canonical"]')?.href || location.href;
document.querySelectorAll("[data-share]").forEach((btn) => btn.addEventListener("click", async () => {
  const status = $("#share-status");
  const say = (t) => { status.textContent = t; const old = btn.textContent; btn.textContent = t; setTimeout(() => (btn.textContent = old), 1800); };
  try {
    if (navigator.share) { await navigator.share({ title: document.title, url: canonical }); return; }
  } catch (e) { if (e && e.name === "AbortError") return; }
  try { await navigator.clipboard.writeText(canonical); say("Link copied"); }
  catch (e) {
    const tmp = h("input", { value: canonical, "aria-label": "Page link", readonly: true, style: "position:fixed;opacity:0" });
    document.body.append(tmp); tmp.select();
    try { document.execCommand("copy"); say("Link copied"); } catch (e2) { say("Copy failed — " + canonical); }
    tmp.remove();
  }
}));

/* ---- data-driven sections, each with its own error state ---- */
const failCard = (node, what, err) => {
  if (!node) return;
  clear(node);
  node.append(h("div", { class: "state-card error", role: "alert" }, `${what} could not be loaded (${err.message}). Everything else on this page still works; the same data is in the repository.`));
};

(async () => {
  try {
    const site = await loadJson("data/site.json");
    const slot = $("#contact-slot");
    const bits = [];
    if (site.contact?.email) bits.push(h("a", { href: `mailto:${site.contact.email}` }, "Email"));
    if (site.contact?.linkedin) bits.push(h("a", { href: site.contact.linkedin, rel: "noopener" }, "LinkedIn"));
    if (slot && bits.length) { slot.hidden = false; bits.forEach((b, i) => { if (i) slot.append(" · "); slot.append(b); }); }
  } catch (e) { /* optional */ }

  let traces = null;
  try {
    traces = await loadJson("data/traces.json");
    const hero = traces.examples.find((x) => x.id === traces.hero_id) || traces.examples[0];
    renderHero($("#hero-trace"), hero, traces.meta);
    initDemo(traces);
  } catch (e) {
    failCard($("#hero-trace"), "The recorded investigation preview", e);
    failCard($("#demo-trace"), "The recorded investigations", e);
  }

  try {
    const m = await loadJson("data/metrics.json");
    renderMetrics(m);
    $("#eval-date").textContent = m.evaluated_at;
    const stamp = $("#build-stamp");
    if (stamp) stamp.textContent = `Evaluation date: ${m.evaluated_at}.`;
  } catch (e) {
    failCard($("#metric-grid"), "The measurements", e);
    $("#ablation")?.setAttribute("hidden", "");
  }
})();
