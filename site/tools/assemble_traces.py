"""Assemble site/src/data/traces.json from raw /investigate recordings.

Usage:  python site/tools/assemble_traces.py <recordings_dir>

<recordings_dir> holds one JSON file per question, each shaped
{"recorded_at": ISO8601, "wall_s": float, "response": <unmodified InvestigateResponse>}
and produced by POSTing the question to a running InsightQuery API (`POST /investigate`).
The raw `response` objects are copied verbatim. Everything *added* by a human lives in clearly
separate fields (`verified`, `reviewer_check`, `reviewer_note`, `badge`) which the page labels as
"not produced by the system". Numbers quoted in those annotations were re-checked with independent
SQL against the same database (see the `verified` strings).
"""
import json
import sys
from pathlib import Path

rec = Path(sys.argv[1])
out = Path(__file__).resolve().parents[1] / "src" / "data" / "traces.json"

# (file stem, id, badge, annotations)
PLAN = [
    ("topn2", "top-crime-types", "verified against the database", {
        "verified": "An independent GROUP BY query returns exactly these five counts: THEFT 57,526; BATTERY 44,303; CRIMINAL DAMAGE 30,098; MOTOR VEHICLE THEFT 29,256; ASSAULT 22,642.",
        "reviewer_note": {"tone": "ok", "text": "The numbers come from SQL, not from the model. The “citation removed” limitation is the citation check firing: there were no retrieved documents, so any citation the model offered was dropped (the removed text is not stored in the response)."},
    }),
    ("monthly2", "monthly-counts", "verified against the database", {
        "verified": "An independent monthly GROUP BY query returns identical counts for all 12 months, summing to 263,841 records.",
        "reviewer_note": {"tone": "ok", "text": "The SQL had no ORDER BY, so rows arrived out of month order; the model's written answer re-sorted them correctly. The chart is drawn in date order."},
    }),
    ("limits", "comparison-limits", "documents only", {}),
    ("codes", "iucr-vs-fbi", "documents only", {}),
    ("hybrid3", "theft-count-undercount", "SQL + documents", {
        "verified": "An independent COUNT of primary_type = 'THEFT' returns 57,526.",
        "reviewer_note": {"tone": "bad", "text": "The number is exactly what SQL returned and both citations are real retrieved documents. But the explanation drifts: it ties theft under-reporting to domestic-violence incidents, which the retrieved passages do not support. Narration is the weakest link, which is why it is labelled LLM-generated."},
    }),
    ("hybrid2", "repair-rejected", "repair demo", {
        "reviewer_note": {"tone": "ok", "text": "The safety design working as intended: the first query failed in PostgreSQL, the model's single repair was re-validated, rejected, and never executed. The final answer admits it cannot determine the result (low confidence) instead of inventing one. Its list of four citations includes documents that merely rank as related; they are retrieved passages, not support for a number."},
    }),
    ("blocked", "blocked-delete", "safety demo", {
        "reviewer_note": {"tone": "bad", "text": "The safety property held: the DELETE was rejected and nothing was executed. The narration did not: the synthesis step answered “No records exist to delete”, which is misleading — it should say the request was blocked. A known weakness of narrating after a rejection; not fixed at the time of this recording."},
    }),
    ("monthly", "wrong-filter", "known failure", {
        "reviewer_check": "The query filtered on description = 'BATTERY'. “BATTERY” is a primary_type value, not a description, so no row matches and every count is 0. An independent query finds 44,303 battery incidents in 2023. The SQL was valid and ran, so the “execution success” metric counts this as a success.",
        "reviewer_note": {"tone": "bad", "text": "The answer repeats the zeros as fact with “high” confidence. This is the failure mode the evaluation section is about: executing without error is not the same as being right."},
    }),
]

examples = []
for stem, ex_id, badge, extra in PLAN:
    d = json.loads((rec / f"{stem}.json").read_text(encoding="utf-8"))
    ex = {"id": ex_id, "badge": badge, "recorded_at": d["recorded_at"], "wall_seconds": d["wall_s"], "response": d["response"]}
    ex.update(extra)
    examples.append(ex)

doc = {
    "hero_id": "top-crime-types",
    "meta": {
        "provider": "Ollama", "model": "llama3.2:3b", "hardware": "CPU only",
        "api": "POST /investigate on the local Docker Compose stack",
        "selection_note": "10 questions were recorded and 8 are shown; the two omitted were near-duplicates of shown ones. Failures are included on purpose. Raw responses are unmodified; only the labelled reviewer notes were added.",
    },
    "examples": examples,
}
out.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"wrote {out} ({len(examples)} examples, {out.stat().st_size // 1024} KiB)")
