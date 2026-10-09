# InsightQuery showcase site

A static, recruiter-facing case study for InsightQuery. Public URL (GitHub Pages):
**https://bhashyamnaidu.github.io/InsightQuery/**

It is deliberately separate from the FastAPI dashboard in `app/`, which it does not touch.
No framework and no npm dependencies: HTML, CSS, ES modules, and a ~100-line Node build.

## What is live and what is recorded

A public static host cannot run PostgreSQL or an LLM, so the **Investigation lab** replays
*recorded* responses of the real `POST /investigate` endpoint (`src/data/traces.json`). Every
screen labels them as recorded, never as generated live. The raw API responses are unmodified;
anything a human added (independent verification, reviewer notes) is stored in separate fields
and shown as "not produced by the system". Metrics are derived at build time from the
committed `docs/*_eval_results.json`, so the page cannot drift from the evaluation outputs.

## Commands

```bash
node site/build.mjs          # -> site/dist  (derives data/metrics.json, stamps URL + content hash)
node site/check.mjs          # links, anchors, repo paths, metadata, secret scan
node site/check.mjs --remote # additionally HEAD-requests every external link and the live URL
node site/serve.mjs 4173     # serves the production build at http://localhost:4173
```

## Re-recording the demo traces

With the Docker stack and Ollama running, POST each question to `/investigate`, save one JSON
file per question (`{"recorded_at", "wall_s", "response"}`), then:

```bash
python site/tools/assemble_traces.py <recordings_dir>   # rewrites src/data/traces.json
node site/build.mjs
```

Edit the annotations in `assemble_traces.py` only after independently re-checking the numbers.

## Social preview

`node site/tools/og/render.mjs` renders `src/og-image.png` (1200x630) from `tools/og/og.html`
with headless Edge/Chrome. The figures in it are the same measured values shown on the page.

## Deployment

`.github/workflows/pages.yml` builds, runs `check.mjs`, and deploys `site/dist` to GitHub Pages on
every push to `master` that touches `site/` or the evaluation outputs. Pages must be set to
"GitHub Actions" as its source (Settings -> Pages). To use a custom domain, set `siteUrl` in
`site/config.json` (must be https and end in `/`) and add the domain in the Pages settings.

## Contact links

`config.json` has empty `contact.email` / `contact.linkedin` fields. They are not shown until
filled in, so no placeholder or broken link is ever rendered.

## Fonts

Inter and JetBrains Mono (SIL OFL 1.1), self-hosted Latin subsets in `src/assets/fonts/`, so
visitors make no third-party requests.
