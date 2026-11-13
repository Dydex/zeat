"""Render site/index.html: every chart, its source and one plain sentence."""

import datetime as dt
import html
import json
import math

from . import charts
from .analysis import EXPLOIT, FEE_SWITCH, TREATED, by_id
from .facts import facts, spct
from .fetch import ROOT

D = dt.date
EPOCH = D(2024, 1, 1)


def ordinal(d):
    return (d - EPOCH).days


def from_ordinal(x):
    return EPOCH + dt.timedelta(int(round(x)))


def month_label(x):
    d = from_ordinal(x)
    return d.strftime("%b %Y")


def usd(v):
    for div, s in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= div:
            return f"${v / div:g}{s}"
    return f"${v:g}"


def weekly_history(daily, start, end):
    """Calendar weeks (Mon–Sun) of summed volume, None when < 4 days observed."""
    d = start - dt.timedelta(start.weekday())
    out = []
    while d + dt.timedelta(6) <= end:
        vals = [daily[d + dt.timedelta(i)] for i in range(7) if d + dt.timedelta(i) in daily]
        out.append((ordinal(d), 7 * sum(vals) / len(vals) if len(vals) >= 4 else None))
        d += dt.timedelta(7)
    return out


def event_chart(test, event, title):
    real = test["_real"]
    ks = sorted(real["synth"])
    wk = lambda k: event + dt.timedelta(7 * k)
    pts_y = [(k, math.exp(real["y"][k]) if real["y"].get(k) is not None else None) for k in ks]
    pts_s = [(k, math.exp(real["synth"][k])) for k in ks]
    return charts.line_chart(
        [dict(name="NEAR Intents (actual)", style="primary", points=pts_y, width=2.5),
         dict(name="Synthetic control (what competitors predict)", style="control",
              points=pts_s, dash="6 4")],
        title=title,
        desc="Weekly volume of NEAR Intents and of its synthetic control, log scale.",
        x_fmt=lambda k: wk(k).strftime("%b %d").replace(" 0", " "),
        y_fmt=usd, log_y=True, vlines=[(0, "event")],
        x_ticks=[k for k in ks if k % 4 == 0])


def gap_chart(test, event):
    real = test["_real"]
    post = test["horizon_weeks"]
    series = []
    for i, p in enumerate(test["_placebos"]):
        series.append(dict(name="Placebo windows", style="muted", width=1, opacity=0.35,
                           legend=i == 0,
                           points=[(k, math.exp(p["gap"][k]) - 1 if k in p["gap"] else None)
                                   for k in range(-26, post)]))
    series.append(dict(name="NEAR Intents vs its control", style="primary", width=2.8,
                       points=[(k, math.exp(real["gap"][k]) - 1 if k in real["gap"] else None)
                               for k in range(-26, post)]))
    ys = [y for s in series for _, y in s["points"] if y is not None]
    hi = min(max(ys), 4.0)
    return charts.line_chart(
        series, title="Gap to control, real vs placebo windows",
        desc="Percent gap between NEAR Intents and its synthetic control, with the same "
             "estimator run at fake event dates in grey.",
        x_fmt=lambda k: f"wk {k:+d}" if k else "event", y_fmt=lambda v: f"{v:+.0%}",
        vlines=[(0, "event")], hline=0, y_range=(max(min(ys), -0.9), hi),
        x_ticks=[k for k in range(-24, post, 4)])


def placebo_dates_chart(test, real_effect_pct, title):
    pts = [(ordinal(D.fromisoformat(d)), e) for d, e in test["placebo_distribution"]["by_date"]]
    return charts.dot_chart(
        pts, title=title,
        desc="Each dot is the estimated effect at a fake event date; the line is the real effect.",
        x_fmt=month_label, y_fmt=lambda v: f"{v:+.0%}", highlight=real_effect_pct, hline=0,
        split=(ordinal(D(2026, 1, 1)), "2026"))


def mature_chart(test, real_effect_pct, since):
    pts = [(ordinal(D.fromisoformat(d)), e) for d, e in test["placebo_distribution"]["by_date"]
           if D.fromisoformat(d) >= since]
    return charts.dot_chart(
        pts, title="T2 placebo effects, 2026 windows only",
        desc="Placebo effects for fake event dates in 2026, after the hypergrowth phase, "
             "with the real effect as a line.",
        x_fmt=month_label, y_fmt=lambda v: f"{v:+.0%}", highlight=real_effect_pct, hline=0)


def robustness_rows(rob):
    rows = [("Leave one control out (range)",
             f"{spct(rob['leave_one_out_range_pct'][0])} to {spct(rob['leave_one_out_range_pct'][1])}"),
            ("Difference-in-differences", spct(rob["did_pct"])),
            ("13-week pre-window", spct(rob["pre_13_weeks_pct"])),
            ("Adding LI.FI, Rango, Bitget (contaminated)", spct(rob["with_contaminated_pct"]))]
    rows += [(f"&nbsp;&nbsp;without {html.escape(k)}", spct(v))
             for k, v in rob["leave_one_out_pct"].items()]
    return "".join(f"<tr><td>{a}</td><td class='num'>{b}</td></tr>" for a, b in rows)


def render(res):
    f = facts(res)
    t1, t2, t3 = (res["tests"][k] for k in ("t1", "t2", "t3"))
    series = res["series"]
    snap = D.fromisoformat(res["snapshot_date"])
    last = snap - dt.timedelta(1)

    hist = weekly_history(series[TREATED], D(2024, 12, 16), last)
    c_hist = charts.line_chart(
        [dict(name="NEAR Intents weekly volume", style="primary", points=hist, width=2.2)],
        title="NEAR Intents weekly volume", desc="Weekly swap volume through NEAR Intents, log scale.",
        x_fmt=month_label, y_fmt=usd, log_y=True,
        vlines=[(ordinal(FEE_SWITCH), "fee switch"), (ordinal(EXPLOIT), "exploit")])

    rev, fees = res["revenue_raw"], series["intents_fees"]
    cap = []
    d = D(2025, 5, 12)
    while d + dt.timedelta(6) <= last:
        fsum = sum(fees.get(d + dt.timedelta(i), 0) for i in range(7))
        rsum = sum(rev.get(d + dt.timedelta(i), 0) for i in range(7))
        cap.append((ordinal(d), rsum / fsum if fsum else None))
        d += dt.timedelta(7)
    c_cap = charts.line_chart(
        [dict(name="Protocol revenue / total fees", style="accent", points=cap, width=2.2)],
        title="Share of fees NEAR keeps", desc="Weekly protocol revenue divided by weekly fees.",
        x_fmt=month_label, y_fmt=lambda v: f"{v:.0%}", hline=0,
        vlines=[(ordinal(FEE_SWITCH), "fee switch")])

    rows = t3["_rows"]
    start3 = D.fromisoformat(t3["window_start"])
    wk3 = lambda k: start3 + dt.timedelta(7 * k)
    venue_series = [
        dict(name=n, style="muted", width=1.2, opacity=0.6, legend=False,
             points=[(r["k"], r["venue_bps"].get(n)) for r in rows])
        for n in ("THORChain", "Chainflip", "Maya Protocol")]
    c_fee = charts.line_chart(
        venue_series + [
            dict(name="Competitors (volume-weighted)", style="control", width=2.2, dash="6 4",
                 points=[(r["k"], r["competitor_bps"]) for r in rows]),
            dict(name="NEAR Intents", style="primary", width=2.6,
                 points=[(r["k"], r["intents_bps"]) for r in rows])],
        title="Fee rate paid by users, basis points",
        desc="Weekly fees divided by weekly volume for NEAR Intents and competitors.",
        x_fmt=lambda k: wk3(k).strftime("%b %d").replace(" 0", " "), y_fmt=lambda v: f"{v:g}",
        x_ticks=list(range(0, 26, 4)),
        y_range=(0, 1.5 * max(max(r["intents_bps"] for r in rows),
                              max(r["competitor_bps"] for r in rows if r["competitor_bps"]))))
    c_share = charts.line_chart(
        [dict(name=f"NEAR Intents share vs {f['t3_share_vs']}", style="primary", width=2.6,
              points=sorted(t3["_share"].items()))],
        title="Volume share", desc="NEAR Intents weekly volume as a share of Intents plus Chainflip.",
        x_fmt=lambda k: wk3(k).strftime("%b %d").replace(" 0", " "), y_fmt=lambda v: f"{v:.0%}",
        x_ticks=list(range(0, 26, 4)))

    manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
    src_rows = "".join(
        f"<tr><td>{html.escape(by_id(e['id'])['name'])}</td><td>{by_id(e['id'])['role']}</td>"
        f"<td><a href='{html.escape(e['url'])}'><code>{html.escape(e['id'])}</code></a></td>"
        f"<td><code>{e['sha256'][:12]}</code></td></tr>"
        for e in manifest["files"])

    def badge(v):
        return f"<span class='badge {v.lower()}'>{v}</span>"

    import os
    live = os.environ.get("MOAT_LIVE") == "1"
    banner = (f"<p class='note'><b>Live rebuild</b> on public data fetched {html.escape(manifest['fetched_at'])}. "
              "The pre-registered analysis is the pinned snapshot in the repository "
              "(<a href='pinned/'>view the pinned build</a>). Verdicts here re-test the same rules on newer data.</p>"
              if live else "")
    from .facts import chain_facts
    from .site_chain import sections
    chain_html, near_html = sections(res, chain_facts(res), ordinal, month_label)
    page = TEMPLATE.format(
        banner=banner, chain_html=chain_html, near_html=near_html,
        **f,
        b1=badge(t1["verdict"]), b2=badge(t2["verdict"]), b3=badge(t3["verdict"]),
        c_hist=c_hist, c_cap=c_cap,
        c_t1=event_chart(t1, FEE_SWITCH, "Fee switch: actual vs synthetic control"),
        c_t1_gap=gap_chart(t1, FEE_SWITCH),
        c_t1_dates=placebo_dates_chart(t1, t1["effect_pct"], "T1 placebo effects by fake event date"),
        c_t2=event_chart(t2, EXPLOIT, "Exploit: actual vs synthetic control"),
        c_t2_gap=gap_chart(t2, EXPLOIT),
        c_t2_dates=placebo_dates_chart(t2, t2["effect_pct"], "T2 placebo effects by fake event date"),
        c_t2_mature=mature_chart(t2, t2["effect_pct"], D(2026, 1, 1)),
        c_fee=c_fee, c_share=c_share,
        rob1=robustness_rows(t1["robustness"]), rob2=robustness_rows(t2["robustness"]),
        src_rows=src_rows, fetched=manifest["fetched_at"],
    )
    out = ROOT / "site" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page)
    return out


def copy_docs():
    """So links on the hosted page resolve without the repo next to it."""
    for name in ("METHODS.md", "THESIS.md"):
        (ROOT / "site" / name).write_text((ROOT / name).read_text())
    (ROOT / "site" / "results.json").write_text((ROOT / "results" / "results.json").read_text())


TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Moat Test: NEAR Intents</title>
<meta name="description" content="Is NEAR Intents' revenue defensible? Three causal tests against a competitor control, rebuilt from public data with one command.">
<style>
:root{{--bg:#fbfaf7;--fg:#1d1d1b;--soft:#5c5c57;--line:#e3e1da;--card:#fff;
--c-primary:#1f6feb;--c-control:#b4540a;--c-muted:#8f8d86;--c-accent:#1a7f5a;--c-bad:#c62828;
--pass:#1a7f5a;--fail:#c62828}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#141413;--fg:#ecebe6;--soft:#a8a69e;
--line:#2e2d2a;--card:#1c1c1a;--c-primary:#6ea8ff;--c-control:#f0a35c;--c-muted:#77756e;--c-accent:#4cc38a;
--pass:#4cc38a;--fail:#ff7b72}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:880px;margin:0 auto;padding:40px 16px 80px}}
h1{{font-size:2.1rem;line-height:1.2;margin:.2em 0 .3em;letter-spacing:-.01em}}
h2{{font-size:1.4rem;margin:2.4em 0 .4em;padding-top:1em;border-top:1px solid var(--line)}}
h3{{font-size:1.05rem;margin:1.6em 0 .3em}}
p,li{{color:var(--fg)}} .soft{{color:var(--soft)}} small{{color:var(--soft)}}
.kicker{{text-transform:uppercase;letter-spacing:.08em;font-size:.78rem;color:var(--soft);margin:0}}
.verdict{{font-size:1.25rem;font-weight:650;margin:.6em 0}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:20px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.card h3{{margin:0 0 .2em;font-size:1rem}} .card .big{{font-size:1.6rem;font-weight:650;font-variant-numeric:tabular-nums}}
.card p{{margin:.3em 0 0;font-size:.92rem;color:var(--soft)}}
.badge{{display:inline-block;font-size:.75rem;font-weight:700;letter-spacing:.06em;padding:2px 8px;border-radius:99px;color:#fff;vertical-align:middle}}
.badge.pass{{background:var(--pass)}} .badge.fail{{background:var(--fail)}}
figure{{margin:14px 0 6px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 10px 4px}}
.chart{{width:100%;height:auto;display:block}}
.chart .grid{{stroke:var(--line);stroke-width:1}} .chart .zero{{stroke:var(--soft);stroke-width:1;stroke-dasharray:3 3}}
.chart .event{{stroke:var(--soft);stroke-width:1.2;stroke-dasharray:2 3}}
.chart .tick{{fill:var(--soft);font-size:11px}} .chart .event-label{{fill:var(--soft);font-size:11px}}
.legend{{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:.82rem;color:var(--soft);padding:4px 6px 6px}}
.key i{{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}}
.shows{{margin:.2em 0 .1em}} .how{{font-size:.86rem;color:var(--soft);margin:0 0 1em}}
table{{border-collapse:collapse;width:100%;font-size:.9rem;margin:10px 0}}
td,th{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
td.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.tablewrap{{overflow-x:auto}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86em}}
pre{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;overflow-x:auto}}
.note{{border-left:3px solid var(--c-control);padding:2px 0 2px 14px;margin:14px 0}}
a{{color:var(--c-primary)}}
</style></head><body><main>

<p class="kicker">NEAR HACKATHON 2026 · Investment Thesis track · data snapshot {snapshot}</p>
<h1>Moat Test: is NEAR Intents' revenue defensible?</h1>
{banner}
<p class="soft">Most NEAR theses ask how much Intents earns. An investor's next question is
whether it can keep earning it. This page tests that three ways, each against a control
built from competitors, so a market-wide move is never mistaken for a NEAR-specific one.
The rules and thresholds were <a href="METHODS.md">pre-registered</a> (<a href="THESIS.md">THESIS.md</a>, <a href="results.json">results.json</a>) and committed before
any result was computed.</p>

<p class="verdict">Verdict: {overall} ({passes} of 3 tests passed)</p>

<div class="cards">
 <div class="card"><h3>T1 Pricing power {b1}</h3><div class="big">{t1_effect}</div>
  <p>Volume vs control in the 8 weeks after the fee switch. NEAR's cut of fees went from {t1_cap_pre} to {t1_cap_post}.</p></div>
 <div class="card"><h3>T2 Trust shock {b2}</h3><div class="big">{t2_effect}</div>
  <p>Volume vs control in weeks 4–5 after the Oct 1 exploit (placebo p = {t2_p}). {t2_robust_note}</p></div>
 <div class="card"><h3>T3 Price premium {b3}</h3><div class="big">{t3_bps_intents} vs {t3_bps_comp} bps</div>
  <p>Median fee rate, Intents vs rivals. Intents was more expensive in only {t3_premium} of {t3_weeks} weeks: it wins on price, not premium.</p></div>
</div>

<h2>What this means for an investor</h2>
<ul>{takeaways}</ul>

<h2>Context</h2>
{c_hist}
<p class="shows"><b>What it shows:</b> Intents grew from almost nothing to a large venue in 2025;
growth flattened in 2026. Both events tested here sit on the mature part of the curve.</p>
<p class="how">Source: DefiLlama <code>near-intents</code> daily volume, summed to Monday–Sunday weeks; weeks with fewer than 4 reported days are left blank.</p>

<h2>T1 Pricing power: the fee switch, Feb 23, 2026 {b1}</h2>
<p>On Feb 23, 2026 NEAR Intents switched on a protocol cut of the fees integrators charge.
If integrators or users had cheaper alternatives, volume should have fallen relative to
competitors.</p>
{c_cap}
<p class="shows"><b>What it shows:</b> the switch was real. NEAR's share of fees rose from
{t1_cap_pre} in the 26 weeks before to {t1_cap_post} in the 8 weeks after, while {switch_note}
({t1_bps_pre} bps before, {t1_bps_post} bps after).</p>
<p class="how">Source: DefiLlama <code>near-intents</code> daily revenue ÷ daily fees, weekly. Because the user price did not move, T1 measures whether integrators and their flow left, not users' price sensitivity.</p>
{c_t1}
<p class="shows"><b>What it shows:</b> in the 8 weeks after the switch Intents ran {t1_effect} relative to
its synthetic control. The pre-registered rule fails T1 only on a loss worse than −10% with
p &lt; 0.10, so T1 passes.</p>
<p class="how">Synthetic control: weights on competitors' log weekly volume fitted on the 26 weeks
before the event ({t1_weights}). Pre-period fit error (RMSPE) is {t1_pre_rmspe} log points, which is loose:
Intents' 2025 hypergrowth is hard for any mix of mature competitors to match.</p>
{c_t1_gap}
{c_t1_dates}
<div class="note"><p><b>Read this with care.</b> {t1_share_above} of the {t1_n} placebo windows show a larger
gain than the real one (median {t1_placebo_median}), because they sit in 2025, when Intents was
outgrowing everything. So the fee switch coincided with Intents' growth lead shrinking.
The T2 placebo series below shows that lead had already fallen towards zero by January 2026, weeks before
the switch, so the slowdown is not evidence that the switch caused it.</p></div>
<h3>Robustness (not used for the verdict)</h3>
<div class="tablewrap"><table><tbody>{rob1}</tbody></table></div>

<h2>T2 Trust shock: the exploit, Oct 1, 2026 {b2}</h2>
<p>On Oct 1, 2026 NEAR Intents was exploited for about $3.8M through a deposit-notification bug.
The contract was paused within about 30 minutes, deposits resumed on Oct 2, and the funds were
returned. A venue with loyal users should see volume come back within weeks.</p>
{c_t2}
<p class="shows"><b>What it shows:</b> {t2_shape} (weeks 0–1: {t2_shock}), then
Intents trailed its control by {t2_effect} in weeks 4–5. Week by week: {t2_weekly}.</p>
<p class="how">Synthetic control fitted on 26 pre-event weeks ({t2_weights}); pre-period RMSPE {t2_pre_rmspe}, a close fit. Recovery statistic = mean gap in weeks 4–5.</p>
{c_t2_gap}
{c_t2_dates}
<p class="how">Each dot re-runs the T2 estimator at a fake event date. In 2025 Intents outgrew every control, so those placebos sit far above zero; that is why the 2026-only view below matters.</p>
{c_t2_mature}
<p class="shows"><b>What it shows:</b> against all {t2_n} placebo windows, p = {t2_p}. Using only
the {t2_n_mature} placebo windows dated 2026, after the hypergrowth phase, p = {t2_p_mature}. Both are below
0.10, so the pre-registered rule fails T2.</p>
{t2_fragile_note}
<h3>Robustness (not used for the verdict)</h3>
<div class="tablewrap"><table><tbody>{rob2}</tbody></table></div>

<h2>T3 Price premium, {t3_window} {b3}</h2>
<p>A business with a moat can charge more than rivals and keep its customers. This test compares
what users pay per dollar swapped on Intents with what they pay on native cross-chain rivals.</p>
{c_fee}
<p class="shows"><b>What it shows:</b> Intents' median fee rate was {t3_bps_intents} bps against
{t3_bps_comp} bps for competitors; Intents was dearer in only {t3_premium} of {t3_weeks} weeks.</p>
<p class="how">Source: DefiLlama daily fees ÷ daily volume, weekly, for each venue. Competitor rate is volume-weighted across THORChain, Chainflip and Maya for the venues reporting that week (grey lines).</p>
{c_share}
<p class="shows"><b>What it shows:</b> Intents' share against {t3_share_vs} went from {t3_share_first} to
{t3_share_last}; trend {t3_slope} a week (90% CI {t3_ci_lo} to {t3_ci_hi}), so share is {t3_share_word}.
Against THORChain and Chainflip over the {t3_sens_n} weeks both report, the trend is {t3_sens} a week.{t3_sens_note}</p>
<p class="how">Share uses only competitors that report every week of the window, because a denominator that gains and loses venues would move on its own. T3 needs both a premium and steady share; the premium is missing, so T3 fails.</p>

{chain_html}
{near_html}

<h2>Limits</h2>
<ul>
<li>All volume and fee data comes from DefiLlama, an aggregator. Its history can be revised; the
snapshot hashes below pin the exact version analysed.</li>
<li>The control pool is small (6 clean series), so placebo-in-space p-values cannot go below about 1/6.</li>
<li>The on-chain figures come from a sample of blocks, not a full census, so each weekly estimate carries
sampling error (bootstrap intervals are in <code>results.json</code>). The sample is pinned in
<code>data/onchain/</code> and can be checked against the chain with <code>python3 -m moat verify-onchain</code>.</li>
<li>Six weeks of post-exploit data is the most the snapshot allows. T2 should be re-run as data arrives;
<code>python3 -m moat refresh</code> then <code>build</code> does exactly that.</li>
</ul>

<h2>Reproduce</h2>
<pre><code>git clone &lt;this repo&gt; &amp;&amp; cd &lt;repo&gt;
python3 -m moat build      # offline: rebuilds results, this page and THESIS.md from the snapshot
python3 -m moat refresh    # optional: download fresh data, then build again
python3 -m unittest        # tests</code></pre>
<p class="soft">Python 3.10+, standard library only. No API keys. Snapshot fetched {fetched}.</p>
<div class="tablewrap"><table><thead><tr><th>Series</th><th>Role</th><th>Source</th><th>sha256</th></tr></thead>
<tbody>{src_rows}</tbody></table></div>
<p class="soft"><small>Not financial advice. Built for NEAR HACKATHON 2026.</small></p>
</main></body></html>
"""
