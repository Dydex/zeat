"""Analyses of the on-chain block sample, and the NEAR-level economics.

These are corroborating, descriptive analyses added after pre-registration
(METHODS.md section 8, item 5). None of them changes a T1–T3 verdict.
"""

import collections
import datetime as dt
import json
import math
import random

from . import stats
from .onchain import BLOCKS, PLAN, load_blocks

UTC = dt.timezone.utc
EXPLOIT = dt.date(2026, 10, 1)
FEE_SWITCH = dt.date(2026, 2, 23)
YOCTO = 10 ** 24


def _plan():
    return json.loads(PLAN.read_text()) if PLAN.exists() else None


def _week_bounds(plan, window):
    w = next(x for x in plan["windows"] if x["name"] == window)
    start, end = dt.date.fromisoformat(w["start"]), dt.date.fromisoformat(w["end"])
    out, d = [], start
    while d < end:
        e = min(d + dt.timedelta(w["step_days"]), end)
        out.append((d, e, plan["anchors"][d.isoformat()], plan["anchors"][e.isoformat()]))
        d = e
    return out


def per_block(row, metric):
    if metric == "intents_executed":
        return row["events"].get("intents_executed", 0)
    if metric == "swaps":
        return row["events"].get("token_diff", 0)
    if metric == "receipts":
        return row["intents_receipts"]
    raise KeyError(metric)


def weekly_index(rows, plan, window, metric, draws=1000, seed=11):
    """Weekly totals = mean per sampled block x blocks in the week (from anchors).

    90% CI by bootstrapping blocks within each week.
    """
    rng = random.Random(seed)
    out = []
    planned = collections.defaultdict(list)
    for b in plan["blocks"]:
        if b["window"] == window:
            planned[b["height"]].append(b)
    for d0, d1, h0, h1 in _week_bounds(plan, window):
        vals = [per_block(rows[h], metric) for h in sorted(planned)
                if h0 <= h < h1 and h in rows]
        if len(vals) < 10:
            out.append(dict(week_start=d0.isoformat(), n=len(vals), total=None))
            continue
        nblocks = h1 - h0
        boots = sorted(stats.mean(rng.choices(vals, k=len(vals))) * nblocks for _ in range(draws))
        out.append(dict(week_start=d0.isoformat(), n=len(vals), blocks_in_week=nblocks,
                        total=stats.mean(vals) * nblocks,
                        ci90=[stats.quantile(boots, 0.05), stats.quantile(boots, 0.95)]))
    return out


def corr(x, y):
    mx, my = stats.mean(x), stats.mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy)


def validation(index, volume_daily):
    """Does DefiLlama's Intents volume move with on-chain activity, week by week?"""
    pairs = []
    for w in index:
        if w["total"] is None or w["total"] <= 0:
            continue
        d0 = dt.date.fromisoformat(w["week_start"])
        vols = [volume_daily.get(d0 + dt.timedelta(i)) for i in range(7)]
        vols = [v for v in vols if v]
        if len(vols) >= 4:
            pairs.append((w["week_start"], math.log(w["total"]), math.log(7 * stats.mean(vols))))
    lv = corr([p[1] for p in pairs], [p[2] for p in pairs]) if len(pairs) > 3 else None
    dl = [(pairs[i][1] - pairs[i - 1][1], pairs[i][2] - pairs[i - 1][2]) for i in range(1, len(pairs))]
    ch = corr([a for a, _ in dl], [b for _, b in dl]) if len(dl) > 3 else None
    return dict(weeks=len(pairs), corr_levels=lv, corr_changes=ch,
                pairs=[dict(week_start=a, log_onchain=b, log_defillama=c) for a, b, c in pairs])


def event_compare(index, volume_daily, event, post_ks):
    """Mean of post weeks vs the 8 weeks before `event`, on-chain and on DefiLlama.

    A before/after comparison with no competitor control (competitors' activity
    lives on other chains), reported beside the same comparison on DefiLlama.
    """
    idx = {w["week_start"]: w["total"] for w in index}

    def vol(d0):
        v = [volume_daily.get(d0 + dt.timedelta(i)) for i in range(7)]
        v = [x for x in v if x]
        return 7 * stats.mean(v) if len(v) >= 4 else None
    ks = list(range(-8, max(post_ks) + 1))
    chain_w = {k: idx.get((event + dt.timedelta(7 * k)).isoformat()) for k in ks}
    llama_w = {k: vol(event + dt.timedelta(7 * k)) for k in ks}

    def change(s):
        pre = [s[k] for k in range(-8, 0) if s.get(k)]
        post = [s[k] for k in post_ks if s.get(k)]
        if len(pre) < 6 or len(post) < len(post_ks):
            return None
        return math.exp(stats.mean(math.log(v) for v in post) - stats.mean(math.log(v) for v in pre)) - 1
    return dict(event=event.isoformat(), post_weeks=list(post_ks),
                onchain_change=change(chain_w), defillama_change=change(llama_w),
                onchain_weekly=chain_w, defillama_weekly=llama_w)


def p_run_anywhere(n, length, q):
    """P(at least one run of >= `length` zeros in n independent draws, P(zero) = q)."""
    if length <= 0:
        return 1.0
    state = [1.0] + [0.0] * (length - 1)  # probability of current trailing run, no hit yet
    hit = 0.0
    for _ in range(n):
        new = [0.0] * length
        for k, p in enumerate(state):
            new[0] += p * (1 - q)
            if k + 1 == length:
                hit += p * q
            else:
                new[k + 1] += p * q
        state = new
    return hit


def pause_timeline(rows, plan):
    pts = sorted((rows[b["height"]]["ts"], rows[b["height"]]["intents_receipts"],
                  rows[b["height"]]["intents_failed"])
                 for b in plan["blocks"] if b["window"] == "pause" and b["height"] in rows)
    if not pts:
        return None
    base = [r for t, r, _ in pts if t < 1790812800000]  # before 2026-10-01 00:00 UTC
    lam = stats.mean(base) if base else None
    run, best, start = 0, (0, None, None), None
    for t, r, _ in pts:
        if r == 0:
            if run == 0:
                start = t
            run += 1
            if run > best[0]:
                best = (run, start, t)
        else:
            run = 0
    # Empty blocks are common even in normal hours, so the chance benchmark uses
    # the empirical share of empty sampled blocks before Oct 1, not a Poisson rate.
    q = sum(r == 0 for r in base) / len(base) if base else None
    iso = lambda ms: dt.datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC") if ms else None
    return dict(samples=len(pts), baseline_per_block=lam, zero_share_before=q,
                longest_zero_run=best[0], zero_run_from=iso(best[1]), zero_run_to=iso(best[2]),
                p_run_anywhere=p_run_anywhere(len(pts), best[0], q) if q is not None else None,
                points=[dict(ts=t, receipts=r, failed=f) for t, r, f in pts])


def solver_concentration(rows, since_ms, min_blocks=3):
    """Repeat counterparties in token_diff events (descriptive).

    Each swap has a user side and a solver side. Users rarely repeat across
    sampled blocks; solvers do. An account in token_diff events in at least
    `min_blocks` different sampled blocks is treated as a repeat counterparty.
    """
    seen = collections.defaultdict(set)
    count = collections.Counter()
    for h, r in rows.items():
        if r["ts"] < since_ms:
            continue
        for a in r["swap_accounts"]:
            seen[a].add(h)
            count[a] += 1
    repeat = {a: c for a, c in count.items() if len(seen[a]) >= min_blocks}
    total = sum(repeat.values())
    if not total:
        return None
    ranked = sorted(repeat.items(), key=lambda kv: -kv[1])
    shares = [c / total for _, c in ranked]
    return dict(accounts_total=len(count), repeat_counterparties=len(repeat),
                appearances=sum(count.values()), repeat_appearances=total,
                top1=shares[0], top3=sum(shares[:3]), top5=sum(shares[:5]),
                hhi=sum(s * s for s in shares),
                top=[dict(account=a, share=c / total) for a, c in ranked[:8]])


def supply(rows, plan):
    """Exact NEAR total supply change between the two supply anchor blocks."""
    hs = [b["height"] for b in plan["blocks"] if b["window"] == "supply"]
    got = [rows[h] for h in hs if h in rows]
    if len(got) < 2:
        return None
    a, b = sorted(got, key=lambda r: r["ts"])
    sa, sb = int(a["total_supply"]), int(b["total_supply"])
    years = (b["ts"] - a["ts"]) / 1000 / (365.25 * 86400)
    return dict(from_height=a["height"], to_height=b["height"],
                from_ts=a["ts"], to_ts=b["ts"], years=years,
                supply_from=sa / YOCTO, supply_to=sb / YOCTO,
                issued=(sb - sa) / YOCTO, growth=(sb / sa) ** (1 / years) - 1)


def economics(sup, series, snap):
    """Intents revenue against the value of NEAR issuance: the long-term link."""
    if not sup:
        return None
    last = snap - dt.timedelta(1)
    days = [last - dt.timedelta(i) for i in range(84)]  # trailing 12 weeks
    s = lambda sid: sum(series[sid].get(d, 0.0) for d in days) * 365 / 84
    rev, fees, vol = s("intents_revenue"), s("intents_fees"), s("intents_volume")
    px = [series["near_price"][d] for d in days[:30] if d in series["near_price"]]
    price = stats.mean(px)
    issued_per_year = sup["issued"] / sup["years"]
    issuance_usd = issued_per_year * price
    return dict(
        window_days=84, price_30d=price, issued_per_year=issued_per_year, issuance_usd=issuance_usd,
        revenue_annual=rev, fees_annual=fees, volume_annual=vol,
        capture=rev / fees if fees else None, fee_bps=1e4 * fees / vol if vol else None,
        coverage=rev / issuance_usd,
        needed_capture=issuance_usd / fees if fees else None,
        needed_volume_multiple=issuance_usd / rev if rev else None,
        needed_volume_at_full_capture=issuance_usd / fees if fees else None,
    )


def run(series, snap):
    plan = _plan()
    if plan is None or not BLOCKS.exists():
        return None
    rows = load_blocks()
    metrics = ("intents_executed", "receipts", "swaps")
    idx = {m: weekly_index(rows, plan, "weekly", m) for m in metrics}
    idx_fs = {m: weekly_index(rows, plan, "feeswitch", m) for m in metrics}
    vol = series["intents_volume"]
    sup = supply(rows, plan)
    recent = int(dt.datetime.combine(snap - dt.timedelta(56), dt.time(), UTC).timestamp() * 1000)
    return dict(
        blocks_sampled=len(rows), blocks_planned=len({b["height"] for b in plan["blocks"]}),
        index=idx, index_feeswitch=idx_fs,
        validation={m: validation(idx[m], vol) for m in metrics},
        validation_feeswitch={m: validation(idx_fs[m], vol) for m in metrics},
        exploit=event_compare(idx["intents_executed"], vol, EXPLOIT, (4, 5)),
        feeswitch=event_compare(idx_fs["intents_executed"], vol, FEE_SWITCH, tuple(range(8))),
        pause=pause_timeline(rows, plan),
        solvers=solver_concentration(rows, recent),
        supply=sup, economics=economics(sup, series, snap),
    )
