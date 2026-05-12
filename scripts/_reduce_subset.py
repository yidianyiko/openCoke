"""Reduce the 40-case subset to ~20 by trimming each bucket."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBSET = ROOT / "artifacts/evidence/reminder-model-compare/2026-05-12-subset.json"
OUTPUT = ROOT / "artifacts/evidence/reminder-model-compare/2026-05-12-subset-20.json"

# Per-bucket target counts (total = 20)
TARGETS = {
    "chinese_clock_nightly":   1,
    "chinese_clock_past_X":    1,
    "chinese_clock_before_X":  1,
    "relative_delay":          2,
    "bare_clock":              2,
    "batch_multi":             1,
    "weekly_recurrence":       1,
    "monthly_or_dayofmonth":   1,
    "bounded_window":          2,
    "clarify_date_only":       2,
    "clarify_completion":      1,
    "clarify_status_only":     1,
    "clarify_ambiguous_time":  1,
    "discussion_meta":         1,
    "discussion_intent":       1,
    "plain_crud_baseline":     1,
}

src = json.loads(SUBSET.read_text(encoding="utf-8"))
reduced_buckets = {}
selected = []
for bucket, members in src["buckets"].items():
    target = TARGETS.get(bucket, len(members))
    picks = members[:target]
    reduced_buckets[bucket] = picks
    selected.extend(picks)
selected = sorted(set(selected))

OUTPUT.write_text(
    json.dumps(
        {"buckets": reduced_buckets, "selected_indices": selected, "total": len(selected)},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(f"Wrote {OUTPUT.name} with {len(selected)} cases")
print(json.dumps(reduced_buckets, ensure_ascii=False, indent=2))
