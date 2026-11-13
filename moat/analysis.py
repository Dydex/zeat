"""The three moat tests, exactly as specified in METHODS.md."""

import datetime as dt
import json
import math

from . import chain, data, stats
from .fetch import MANIFEST, ROOT
from .sources import COMPETITORS, FEE_PAIRS, SOURCES, by_id

D = dt.date
TREATED = "intents_volume"
DONORS = [s["id"] for s in SOURCES if s["role"] == "donor"]
CONTAMINATED = [s["id"] for s in SOURCES if s["role"] == "contaminated"]

FEE_SWITCH = D(2026, 2, 23)
EXPLOIT = D(2026, 10, 1)
P = 26             # pre-window, weeks
LOSS = math.log(0.90)   # -10% threshold, in log points
ALPHA = 0.10
MIN_FIT_WEEKS = 10


def pct(log_effect):
    return math.exp(log_effect) - 1


# --------------------------------------------------------------------------
# Synthetic control around one event
# --------------------------------------------------------------------------

def sc_event(series, treated, donors, event, pre, post, stat_weeks, last_day):
    """Fit a synthetic control for `treated` around `event`.

    Returns None when the rules leave too little data to fit.
    """
    y = data.log_weeks(data.event_weeks(series[treated], event, -pre, post, last_day))
    if any(y.get(k) is None for k in range(post)):
        return None
    logs = {d: data.log_weeks(data.event_weeks(series[d], event, -pre, post, last_day))
            for d in donors}
    pre_ks = list(range(-pre, 0))
    eligible = [d for d in donors
                if sum(logs[d].get(k) is not None for k in pre_ks) >= 0.8 * pre
                and all(logs[d].get(k) is not None for k in range(post))]
    if not eligible:
        return None
    fit_ks = [k for k in pre_ks
              if y.get(k) is not None and all(logs[d].get(k) is not None for d in eligible)]
    if len(fit_ks) < MIN_FIT_WEEKS:
        return None
    X = [[logs[d][k] for d in eligible] for k in fit_ks]
    w, a = stats.synthetic_control([y[k] for k in fit_ks], X)

    synth, gap = {}, {}
    for k in range(-pre, post):
        if all(logs[d].get(k) is not None for d in eligible):
            synth[k] = a + sum(wj * logs[d][k] for wj, d in zip(w, eligible))
            if y.get(k) is not None:
                gap[k] = y[k] - synth[k]
    pre_r = stats.rmspe(gap[k] for k in fit_ks)
    post_r = stats.rmspe(gap[k] for k in range(post))
    return dict(
        event=event.isoformat(), weights=dict(zip(eligible, w)), intercept=a,
        fit_weeks=len(fit_ks), y=y, synth=synth, gap=gap,
        effect=stats.mean(gap[k] for k in stat_weeks),
        pre_rmspe=pre_r, post_rmspe=post_r,
        ratio=post_r / pre_r if pre_r > 0 else float("inf"),
    )


def placebo_in_time(series, treated, donors, event, pre, post, stat_weeks):
    """Re-run the estimator at fake dates whose whole window ends before `event`."""
    first = data.first_day(series[treated])
    out = []
    m = post
    while True:
        fake = event - dt.timedelta(7 * m)
        if fake - dt.timedelta(7 * pre) < first:
            break
        r = sc_event(series, treated, donors, fake, pre, post, stat_weeks,
                     last_day=event - dt.timedelta(1))
        if r is not None:
            out.append(r)
        m += 1
    return out


def placebo_in_space(series, real, pre, post, stat_weeks, last_day):
    """Treat each eligible donor as if it had the event."""
    eligible = list(real["weights"])
    rows = [dict(id=TREATED, ratio=real["ratio"], effect=real["effect"])]
    for d in eligible:
        others = [o for o in eligible if o != d]
        if not others:
            continue
        r = sc_event(series, d, others, D.fromisoformat(real["event"]), pre, post,
                     stat_weeks, last_day)
        if r is not None:
            rows.append(dict(id=d, ratio=r["ratio"], effect=r["effect"]))
    rows.sort(key=lambda r: -r["ratio"])
    rank = next(i for i, r in enumerate(rows, 1) if r["id"] == TREATED)
    return dict(rank=rank, n=len(rows), p=rank / len(rows), rows=rows)


def did(series, donors, event, pre, post, last_day):
    """log(Intents) - mean log(donors): post mean minus pre mean."""
    y = data.log_weeks(data.event_weeks(series[TREATED], event, -pre, post, last_day))
    logs = [data.log_weeks(data.event_weeks(series[d], event, -pre, post, last_day))
            for d in donors]

    def diff(ks):
        vals = [y[k] - stats.mean(l[k] for l in logs) for k in ks
                if y.get(k) is not None and all(l.get(k) is not None for l in logs)]
        return stats.mean(vals)
    return diff(range(post)) - diff(range(-pre, 0))


def event_test(series, event, post, stat_weeks, last_day):
    """Primary estimate, inference and robustness for one event."""
    real = sc_event(series, TREATED, DONORS, event, P, post, stat_weeks, last_day)
    placebos = placebo_in_time(series, TREATED, DONORS, event, P, post, stat_weeks)
    effects = [p["effect"] for p in placebos]
    p_loss = sum(e <= real["effect"] for e in effects) / len(effects)
    space = placebo_in_space(series, real, P, post, stat_weeks, last_day)

    loo = {}
    for d in real["weights"]:
        r = sc_event(series, TREATED, [x for x in DONORS if x != d], event, P, post,
                     stat_weeks, last_day)
        if r is not None:
            loo[d] = r["effect"]
    short = sc_event(series, TREATED, DONORS, event, 13, post, stat_weeks, last_day)
    contaminated = sc_event(series, TREATED, DONORS + CONTAMINATED, event, P, post,
                            stat_weeks, last_day)
    # All robustness numbers are reported as percentage effects.
    robustness = dict(
        leave_one_out_pct={by_id(d)["name"]: pct(e) for d, e in loo.items()},
        leave_one_out_range_pct=[pct(min(loo.values())), pct(max(loo.values()))] if loo else None,
        did_pct=pct(did(series, list(real["weights"]), event, P, post, last_day)),
        pre_13_weeks_pct=pct(short["effect"]) if short else None,
        with_contaminated_pct=pct(contaminated["effect"]) if contaminated else None,
    )
    return real, placebos, p_loss, space, robustness


# --------------------------------------------------------------------------
# T1 and T2
# --------------------------------------------------------------------------

def weekly_sum(daily, start, days):
    return sum(daily.get(start + dt.timedelta(i), 0.0) for i in range(days))


def first_stage(series, revenue_raw):
    """Capture rate (revenue / fees) and fee rate (fees / volume) around the switch."""
    def window(start, days):
        fees = weekly_sum(series["intents_fees"], start, days)
        rev = weekly_sum(revenue_raw, start, days)
        vol = weekly_sum(series[TREATED], start, days)
        return dict(capture=rev / fees if fees else None,
                    fee_bps=1e4 * fees / vol if vol else None)
    pre = window(FEE_SWITCH - dt.timedelta(7 * P), 7 * P)
    post = window(FEE_SWITCH, 7 * 8)
    return dict(pre=pre, post=post)


MATURE_FROM = D(2026, 1, 1)


def placebo_summary(placebos, real_effect):
    """Where the real effect sits in the placebo distribution.

    Diagnostic only (METHODS.md section 8, item 3): also reports the p-value
    using placebos dated 2026 or later, after Intents' 2025 hypergrowth.
    """
    e = [p["effect"] for p in placebos]
    mature = [p["effect"] for p in placebos if D.fromisoformat(p["event"]) >= MATURE_FROM]
    return dict(median_pct=pct(stats.quantile(e, 0.5)), p10_pct=pct(stats.quantile(e, 0.1)),
                p90_pct=pct(stats.quantile(e, 0.9)), min_pct=pct(min(e)), max_pct=pct(max(e)),
                n_mature=len(mature),
                p_loss_mature=(sum(x <= real_effect for x in mature) / len(mature)) if mature else None,
                by_date=[(p["event"], pct(p["effect"])) for p in placebos])


def t1(series, revenue_raw, last_day):
    real, placebos, p, space, rob = event_test(series, FEE_SWITCH, 8, range(8), last_day)
    fail = real["effect"] < LOSS and p < ALPHA
    return dict(
        name="Pricing power", event=FEE_SWITCH.isoformat(), horizon_weeks=8,
        effect=real["effect"], effect_pct=pct(real["effect"]),
        p_loss=p, n_placebos=len(placebos), placebo_in_space=space,
        placebo_distribution=placebo_summary(placebos, real["effect"]),
        first_stage=first_stage(series, revenue_raw),
        robustness=rob, verdict="FAIL" if fail else "PASS",
        fit=_fit_summary(real), _real=real, _placebos=placebos,
    )


def t2(series, last_day):
    real, placebos, p, space, rob = event_test(series, EXPLOIT, 6, (4, 5), last_day)
    shock = stats.mean(real["gap"][k] for k in (0, 1))
    fail = real["effect"] < LOSS and p < ALPHA
    return dict(
        name="Trust shock", event=EXPLOIT.isoformat(), horizon_weeks=6,
        shock=shock, shock_pct=pct(shock),
        effect=real["effect"], effect_pct=pct(real["effect"]),
        weekly_gap_pct={k: pct(real["gap"][k]) for k in range(6)},
        p_loss=p, n_placebos=len(placebos), placebo_in_space=space,
        placebo_distribution=placebo_summary(placebos, real["effect"]),
        robustness=rob, verdict="FAIL" if fail else "PASS",
        fit=_fit_summary(real), _real=real, _placebos=placebos,
    )


def _fit_summary(real):
    return dict(weights={by_id(k)["name"]: round(v, 4) for k, v in real["weights"].items()
                         if v >= 1e-4},
                fit_weeks=real["fit_weeks"], pre_rmspe=real["pre_rmspe"],
                post_rmspe=real["post_rmspe"])


# --------------------------------------------------------------------------
# T3
# --------------------------------------------------------------------------

def t3(series, snap):
    start = snap - dt.timedelta(7 * P)
    last_day = snap - dt.timedelta(1)
    weeks = {}
    for name, (fee_id, vol_id) in FEE_PAIRS.items():
        f = data.event_weeks(series[fee_id], start, 0, P, last_day)
        v = data.event_weeks(series[vol_id], start, 0, P, last_day)
        weeks[name] = {k: (f[k], v[k]) for k in range(P)
                       if f.get(k) is not None and v.get(k) is not None}

    rows = []
    for k in range(P):
        if k not in weeks["NEAR Intents"]:
            continue
        fi, vi = weeks["NEAR Intents"][k]
        comp = [weeks[n][k] for n in FEE_PAIRS if n != "NEAR Intents" and k in weeks[n]]
        comp_rate = 1e4 * sum(f for f, _ in comp) / sum(v for _, v in comp) if comp else None
        rows.append(dict(k=k, week_start=(start + dt.timedelta(7 * k)).isoformat(),
                         intents_bps=1e4 * fi / vi, competitor_bps=comp_rate,
                         venues=len(comp),
                         venue_bps={n: 1e4 * weeks[n][k][0] / weeks[n][k][1]
                                    for n in FEE_PAIRS if k in weeks[n]}))
    rated = [r for r in rows if r["competitor_bps"] is not None]
    premium_weeks = sum(r["intents_bps"] > r["competitor_bps"] for r in rated) / len(rated)

    # Share against competitors observed in every week (a changing denominator
    # would move the share for reasons unrelated to Intents).
    vol = {i: data.event_weeks(series[i], start, 0, P, last_day) for i in [TREATED] + COMPETITORS}
    full = [c for c in COMPETITORS if all(vol[c].get(k) is not None for k in range(P))]
    ks = [k for k in range(P) if vol[TREATED].get(k) is not None]
    share = {k: vol[TREATED][k] / (vol[TREATED][k] + sum(vol[c][k] for c in full)) for k in ks}
    x, y = ks, [math.log(share[k]) for k in ks]
    slope = stats.ols(x, y)[1]
    lo, hi = stats.block_bootstrap_slope(x, y)

    # Sensitivity: weeks where THORChain and Chainflip are both observed.
    both = ["thorchain_volume", "chainflip_volume"]
    ks2 = [k for k in ks if all(vol[c].get(k) is not None for c in both)]
    share2 = {k: vol[TREATED][k] / (vol[TREATED][k] + sum(vol[c][k] for c in both)) for k in ks2}
    slope2 = stats.ols(ks2, [math.log(share2[k]) for k in ks2])[1] if len(ks2) > 2 else None

    # Descriptive elasticity: change in log share vs change in log relative price.
    rel = {r["k"]: math.log(r["intents_bps"] / r["competitor_bps"]) for r in rated}
    pairs = [(rel[k] - rel[k - 1], math.log(share[k]) - math.log(share[k - 1]))
             for k in ks if k in rel and k - 1 in rel and k - 1 in share]
    elasticity = stats.ols([a for a, _ in pairs], [b for _, b in pairs])[1] if len(pairs) > 2 else None

    passed = premium_weeks >= 0.75 and hi >= 0
    return dict(
        name="Price premium", window_start=start.isoformat(), window_end=last_day.isoformat(),
        premium_weeks=premium_weeks, weeks_rated=len(rated),
        median_intents_bps=stats.quantile([r["intents_bps"] for r in rated], 0.5),
        median_competitor_bps=stats.quantile([r["competitor_bps"] for r in rated], 0.5),
        share_competitors=[by_id(c)["name"] for c in full],
        share_first=share[ks[0]], share_last=share[ks[-1]],
        share_slope_per_week=slope, share_slope_ci90=[lo, hi],
        share_slope_pct_per_week=pct(slope),
        sensitivity_share_slope_thor_chainflip=slope2, sensitivity_weeks=len(ks2),
        elasticity_descriptive=elasticity,
        verdict="PASS" if passed else "FAIL",
        _rows=rows, _share={rows_k: share[rows_k] for rows_k in ks},
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def run():
    snap, series = data.load_snapshot()
    last_day = snap - dt.timedelta(1)
    manifest = json.loads(MANIFEST.read_text())
    rev_file = next(e["file"] for e in manifest["files"] if e["id"] == "intents_revenue")
    revenue_raw = data.parse_chart(json.loads((ROOT / rev_file).read_text()),
                                   before=snap, keep_zero=True)

    r1 = t1(series, revenue_raw, last_day)
    r2 = t2(series, last_day)
    r3 = t3(series, snap)
    onchain = chain.run(series, snap)
    passes = sum(r["verdict"] == "PASS" for r in (r1, r2, r3))
    overall = {3: "Strong moat evidence", 2: "Moderate moat evidence"}.get(passes, "Weak moat evidence")
    return dict(snapshot_date=snap.isoformat(), fetched_at=manifest["fetched_at"],
                tests=dict(t1=r1, t2=r2, t3=r3), passes=passes, overall=overall,
                chain=onchain,
                series=series, revenue_raw=revenue_raw)


def public(results):
    """Strip private (underscore) keys and raw series for results.json."""
    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items() if not str(k).startswith("_")}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, float):
            return round(o, 6)
        return o
    keep = {k: v for k, v in results.items() if k not in ("series", "revenue_raw")}
    return clean(keep)


def write_results(results):
    out = ROOT / "results" / "results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(public(results), indent=2, sort_keys=True) + "\n")
    return out
