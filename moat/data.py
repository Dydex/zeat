"""Load the verified snapshot and turn daily series into event-weeks.

Implements the cleaning rules in METHODS.md section 3.
"""

import datetime as dt
import json
import math

from .fetch import MANIFEST, ROOT, verify

Day = dt.date


def load_snapshot():
    """Return (snapshot_date, {source_id: {date: value}}) after hash checks."""
    manifest = verify(json.loads(MANIFEST.read_text()))
    snap = Day.fromisoformat(manifest["snapshot_date"])
    series = {}
    for e in manifest["files"]:
        raw = json.loads((ROOT / e["file"]).read_text())
        series[e["id"]] = parse_chart(raw, before=snap)
    return snap, series


def parse_chart(raw, before, keep_zero=False):
    """DefiLlama `totalDataChart` -> {date: float}. Rule 1 and rule 2.

    keep_zero=True is for the revenue series only, where a zero is a real
    "no revenue taken" day rather than a reporting gap (METHODS.md section 8).
    """
    out = {}
    for ts, value in raw.get("totalDataChart") or []:
        d = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()
        if d >= before:
            continue
        if value is None:
            continue
        v = float(value)
        if v > 0 or (keep_zero and v == 0):  # zero = missing, never imputed
            out[d] = v
    return out


def week_value(daily, start, min_days=4):
    """Rule 3: 7 x mean of observed days, or None if fewer than min_days."""
    vals = [daily[start + dt.timedelta(i)] for i in range(7)
            if start + dt.timedelta(i) in daily]
    if len(vals) < min_days:
        return None
    return 7.0 * sum(vals) / len(vals)


def event_weeks(daily, event, k_from, k_to, last_day):
    """{k: weekly value or None} for k in [k_from, k_to).

    Weeks extending past `last_day` (incomplete) are omitted entirely.
    """
    out = {}
    for k in range(k_from, k_to):
        start = event + dt.timedelta(7 * k)
        if start + dt.timedelta(6) > last_day:
            continue
        out[k] = week_value(daily, start)
    return out


def log_weeks(weeks):
    return {k: (math.log(v) if v else None) for k, v in weeks.items()}


def first_day(daily):
    return min(daily) if daily else None
