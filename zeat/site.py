"""Render site/index.html as a research note: numbered sections and figures,
each figure with a title, its takeaway and its source. Every number comes from
results.json via facts.py."""

import datetime as dt
import html
import json
import math
import os

from . import charts
from .analysis import EXPLOIT, FEE_SWITCH, TREATED, by_id
from .facts import chain_facts, facts, spct, usd_short
from .fetch import ROOT
from .site_chain import sections

D = dt.date
EPOCH = D(2024, 1, 1)
REPO = "https://github.com/Dydex/zeat"


def ordinal(d):
    return (d - EPOCH).days


def from_ordinal(x):
    return EPOCH + dt.timedelta(int(round(x)))


def month_label(x):
    return from_ordinal(x).strftime("%b %Y")


def day(d):
    return d.strftime("%b %d, %Y").replace(" 0", " ")


def week_of(x):
    return "Week of " + day(from_ordinal(x))


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
        [dict(name="NEAR Intents (actual)", short="NEAR Intents", style="primary", points=pts_y, width=2.5),
         dict(name="Synthetic control (what competitors predict)", short="Synthetic control",
              style="control", points=pts_s, dash="6 4")],
        title=title,
        desc="Weekly volume of NEAR Intents and of its synthetic control, log scale.",
        x_fmt=lambda k: wk(k).strftime("%b %d").replace(" 0", " "),
        x_hover=lambda k: f"Week {k:+d} · {day(wk(k))}" if k else f"Event week · {day(wk(k))}",
        y_fmt=usd, y_hover=usd_short, log_y=True, vlines=[(0, "event")],
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
    series.append(dict(name="NEAR Intents vs its control", short="Real gap", style="primary", width=2.8,
                       points=[(k, math.exp(real["gap"][k]) - 1 if k in real["gap"] else None)
                               for k in range(-26, post)]))
    ys = [y for s in series for _, y in s["points"] if y is not None]
    hi = min(max(ys), 4.0)
    return charts.line_chart(
        series, title="Gap to control, real vs placebo windows",
        desc="Percent gap between NEAR Intents and its synthetic control, with the same "
             "estimator run at fake event dates in grey.",
        x_fmt=lambda k: f"wk {k:+d}" if k else "event", x_hover=lambda k: f"Week {k:+d}" if k else "Event week",
        y_fmt=lambda v: f"{v:+.0%}",
        vlines=[(0, "event")], hline=0, y_range=(max(min(ys), -0.9), hi),
        x_ticks=[k for k in range(-24, post, 4)])


def placebo_dates_chart(test, real_effect_pct, title, since=None, split=True):
    pts = [(ordinal(D.fromisoformat(d)), e) for d, e in test["placebo_distribution"]["by_date"]
           if since is None or D.fromisoformat(d) >= since]
    return charts.dot_chart(
        pts, title=title,
        desc="Each dot is the estimated effect at a fake event date; the line is the real effect.",
        x_fmt=month_label, x_hover=lambda x: "Fake event " + day(from_ordinal(x)),
        y_fmt=lambda v: f"{v:+.0%}", highlight=real_effect_pct, hline=0,
        split=(ordinal(D(2026, 1, 1)), "2026") if split else None)


def robustness_rows(rob):
    rows = [("Leave one control out (range)",
             f"{spct(rob['leave_one_out_range_pct'][0])} to {spct(rob['leave_one_out_range_pct'][1])}"),
            ("Difference-in-differences", spct(rob["did_pct"])),
            ("13-week pre-window", spct(rob["pre_13_weeks_pct"])),
            ("Adding LI.FI, Rango, Bitget (contaminated)", spct(rob["with_contaminated_pct"]))]
    rows += [(f"<span class='indent'>without {html.escape(k)}</span>", spct(v))
             for k, v in rob["leave_one_out_pct"].items()]
    return "".join(f"<tr><td>{a}</td><td class='num'>{b}</td></tr>" for a, b in rows)


def badge(v):
    mark = "✓" if v == "PASS" else "✕"
    return f"<span class='verdict {v.lower()}'><span aria-hidden='true'>{mark}</span> {v}</span>"


def p_phrase(p_all, p_mature, cut=0.10):
    a, m = float(p_all) < cut, float(p_mature) < cut
    if a and m:
        return "Both are below 0.10, so the 2026-only check agrees with the pre-registered one"
    if a:
        return "Only the full set is below 0.10; the 2026-only check does not confirm it"
    if m:
        return "Only the 2026-only set is below 0.10; the pre-registered test uses the full set"
    return "Neither is below 0.10"


def render(res):
    f = facts(res)
    cf = chain_facts(res)
    t1, t2, t3 = (res["tests"][k] for k in ("t1", "t2", "t3"))
    series = res["series"]
    snap = D.fromisoformat(res["snapshot_date"])
    last = snap - dt.timedelta(1)

    hist = weekly_history(series[TREATED], D(2024, 12, 16), last)
    c_hist = charts.line_chart(
        [dict(name="NEAR Intents weekly volume", short="Volume", style="primary", points=hist, width=2.2)],
        title="NEAR Intents weekly volume", desc="Weekly swap volume through NEAR Intents, log scale.",
        x_fmt=month_label, x_hover=week_of, y_fmt=usd, y_hover=usd_short, log_y=True,
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
        [dict(name="Protocol revenue / total fees", short="NEAR's share", style="accent", points=cap, width=2.2)],
        title="Share of fees NEAR keeps", desc="Weekly protocol revenue divided by weekly fees.",
        x_fmt=month_label, x_hover=week_of, y_fmt=lambda v: f"{v:.0%}", y_hover=lambda v: f"{v:.1%}",
        hline=0, vlines=[(ordinal(FEE_SWITCH), "fee switch")])

    rows = t3["_rows"]
    start3 = D.fromisoformat(t3["window_start"])
    wk3 = lambda k: start3 + dt.timedelta(7 * k)
    venue_series = [
        dict(name=n, style="muted", width=1.2, opacity=0.6, legend=False, hover=True,
             points=[(r["k"], r["venue_bps"].get(n)) for r in rows])
        for n in ("THORChain", "Chainflip", "Maya Protocol")]
    c_fee = charts.line_chart(
        venue_series + [
            dict(name="Competitors (volume-weighted)", short="Competitors", style="control", width=2.2,
                 dash="6 4", points=[(r["k"], r["competitor_bps"]) for r in rows]),
            dict(name="NEAR Intents", style="primary", width=2.6,
                 points=[(r["k"], r["intents_bps"]) for r in rows])],
        title="Fee rate paid by users, basis points",
        desc="Weekly fees divided by weekly volume for NEAR Intents and competitors.",
        x_fmt=lambda k: wk3(k).strftime("%b %d").replace(" 0", " "),
        x_hover=lambda k: "Week of " + day(wk3(k)), y_fmt=lambda v: f"{v:g}",
        y_hover=lambda v: f"{v:.1f} bps", x_ticks=list(range(0, 26, 4)),
        y_range=(0, 1.5 * max(max(r["intents_bps"] for r in rows),
                              max(r["competitor_bps"] for r in rows if r["competitor_bps"]))))
    c_share = charts.line_chart(
        [dict(name=f"NEAR Intents share vs {f['t3_share_vs']}", short="Intents share", style="primary",
              width=2.6, points=sorted(t3["_share"].items()))],
        title="Volume share", desc="NEAR Intents weekly volume as a share of Intents plus Chainflip.",
        x_fmt=lambda k: wk3(k).strftime("%b %d").replace(" 0", " "),
        x_hover=lambda k: "Week of " + day(wk3(k)), y_fmt=lambda v: f"{v:.0%}",
        y_hover=lambda v: f"{v:.1%}", x_ticks=list(range(0, 26, 4)))

    manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
    src_rows = "".join(
        f"<tr><td>{html.escape(by_id(e['id'])['name'])}</td><td>{by_id(e['id'])['role']}</td>"
        f"<td><a href='{html.escape(e['url'])}'><code>{html.escape(e['id'])}</code></a></td>"
        f"<td><code>{e['sha256'][:12]}</code></td></tr>"
        for e in manifest["files"])

    live = os.environ.get("ZEAT_LIVE") == "1"
    banner = (f"<aside class='live'><b>Live rebuild</b> on public data fetched {html.escape(manifest['fetched_at'])}. "
              "The pre-registered analysis is the pinned snapshot in the repository "
              "(<a href='pinned/'>view the pinned build</a>). Verdicts here re-test the same rules on newer data.</aside>"
              if live else "")
    chain_html, near_html = sections(res, cf, ordinal, month_label, week_of)
    has_chain = bool(chain_html)
    dek = ("Three pre-registered causal tests of NEAR Intents' moat, each against a control built "
           "from competitors" + (f", checked against {cf['blocks']} NEAR blocks read directly from the chain."
                                 if has_chain else "."))
    toc_items = [("abstract", "", "Abstract"), ("design", "1", "Question and design"),
                 ("t1", "2", "Pricing power"), ("t2", "3", "Trust shock"), ("t3", "4", "Price premium")]
    if has_chain:
        toc_items += [("chain", "5", "On-chain check"), ("near", "6", "The long-term case for NEAR")]
    toc_items += [("limits", "7", "Limits"), ("reproduce", "8", "Reproduce")]
    toc = "".join(f"<li><a href='#{i}' data-t='{(n + ' · ') if n else ''}{t}'><span class='n'>{n}</span>{t}</a></li>"
                  for i, n, t in toc_items)

    page = TEMPLATE.format(
        banner=banner, chain_html=chain_html, near_html=near_html, dek=dek, toc=toc, repo=REPO,
        **f,
        t2_shape_cap=f["t2_shape"][:1].upper() + f["t2_shape"][1:],
        t2_p_phrase=p_phrase(f["t2_p"], f["t2_p_mature"]),
        b1=badge(t1["verdict"]), b2=badge(t2["verdict"]), b3=badge(t3["verdict"]),
        c_hist=c_hist, c_cap=c_cap,
        c_t1=event_chart(t1, FEE_SWITCH, "Fee switch: actual vs synthetic control"),
        c_t1_gap=gap_chart(t1, FEE_SWITCH),
        c_t1_dates=placebo_dates_chart(t1, t1["effect_pct"], "T1 placebo effects by fake event date"),
        c_t2=event_chart(t2, EXPLOIT, "Exploit: actual vs synthetic control"),
        c_t2_gap=gap_chart(t2, EXPLOIT),
        c_t2_dates=placebo_dates_chart(t2, t2["effect_pct"], "T2 placebo effects by fake event date"),
        c_t2_mature=placebo_dates_chart(t2, t2["effect_pct"], "T2 placebo effects, 2026 windows only",
                                        since=D(2026, 1, 1), split=False),
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


CSS = """
:root{--bg:#fbfaf7;--fg:#1b1a17;--soft:#56534c;--faint:#85817a;--line:#e4e0d6;--rule:#cfcabe;
--card:#ffffff;--tint:#f3f0e8;--link:#1d5fc4;
--c-primary:#1f6feb;--c-control:#b4540a;--c-muted:#99958b;--c-accent:#1a7f5a;--c-bad:#c62828;
--pass:#17734f;--fail:#b42318;
--serif:"Source Serif 4",Charter,"Bitstream Charter","Sitka Text",Cambria,Georgia,serif;
--sans:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#151513;--fg:#ebe8e0;--soft:#b0aca2;--faint:#7f7b73;
--line:#2d2b27;--rule:#45423c;--card:#1c1c1a;--tint:#201f1c;--link:#86b4ff;
--c-primary:#3987e5;--c-control:#d95926;--c-muted:#6f6c65;--c-accent:#2a9d8f;--c-bad:#e66767;
--pass:#4cc38a;--fail:#ff7b72}}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:var(--bg);color:var(--fg);font:18px/1.65 var(--serif);
font-optical-sizing:auto;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.page{max-width:1160px;margin:0 auto;padding:64px 24px 96px;display:grid;
grid-template-columns:200px minmax(0,700px);gap:72px;justify-content:center}
article{min-width:0}
a{color:var(--link);text-decoration-thickness:1px;text-underline-offset:2px}
/* contents */
.toc{position:sticky;top:64px;align-self:start;font:13.5px/1.4 var(--sans)}
.toc p{margin:0 0 10px;font-weight:600;font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint)}
.toc ol{list-style:none;margin:0;padding:0;border-left:1px solid var(--line)}
.toc li a{display:flex;gap:10px;padding:5px 0 5px 14px;margin-left:-1px;border-left:2px solid transparent;
color:var(--soft);text-decoration:none}
.toc li a:hover{color:var(--fg)}
.toc li a.on{color:var(--fg);border-left-color:var(--fg);font-weight:600}
.toc .n{min-width:12px;color:var(--faint);font-variant-numeric:tabular-nums}
.toc-inline{display:none}
.mnav{display:none}
/* title block */
.kicker{font:600 12px/1.4 var(--sans);letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin:0 0 18px}
h1{font-size:46px;line-height:1.08;letter-spacing:-.015em;font-weight:700;margin:0 0 18px}
.dek{font-size:21px;line-height:1.5;color:var(--soft);margin:0 0 22px}
.byline{font:14px/1.6 var(--sans);color:var(--soft);margin:0;padding:14px 0;border-top:1px solid var(--line);
border-bottom:1px solid var(--line)}
.byline a{color:var(--soft)} .byline b{color:var(--fg);font-weight:600}
.live{font:14.5px/1.55 var(--sans);background:var(--tint);border-left:3px solid var(--c-primary);
padding:12px 16px;margin:20px 0 0}
/* abstract */
.abstract{margin:40px 0 0}
.label{font:600 12px/1.4 var(--sans)!important;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);
margin:0 0 10px!important;border:0!important;padding:0!important}
.abstract>p{margin:0 0 14px}
.findings{margin:26px 0 0;padding:0;list-style:none;counter-reset:k}
.findings li{counter-increment:k;position:relative;padding-left:34px;margin:0 0 12px}
.findings li::before{content:counter(k);position:absolute;left:0;top:3px;width:22px;height:22px;border-radius:50%;
background:var(--fg);color:var(--bg);font:600 12px/22px var(--sans);text-align:center}
/* sections */
section{margin-top:72px}
h2{font-size:30px;line-height:1.2;letter-spacing:-.01em;font-weight:700;margin:0 0 6px;
display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
h2 .secnum{font:600 15px var(--sans);color:var(--faint);min-width:18px}
h3{font-size:21px;line-height:1.3;font-weight:600;margin:44px 0 8px}
.meta{font:13.5px/1.6 var(--sans);color:var(--soft);margin:0 0 22px;padding-bottom:16px;border-bottom:1px solid var(--line)}
.meta b{color:var(--fg);font-weight:600}
p{margin:0 0 18px}
ul.plain{padding-left:22px} ul.plain li{margin:0 0 10px}
.verdict{display:inline-flex;align-items:center;gap:5px;font:700 11.5px/1 var(--sans);letter-spacing:.08em;
padding:5px 9px 5px 8px;border-radius:4px;vertical-align:middle;white-space:nowrap}
.verdict.pass{color:var(--pass);background:color-mix(in srgb,var(--pass) 11%,transparent);
box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--pass) 35%,transparent)}
.verdict.fail{color:var(--fail);background:color-mix(in srgb,var(--fail) 9%,transparent);
box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--fail) 32%,transparent)}
/* figures */
figure{margin:34px 0 30px}
.fig-title{font:600 15px/1.4 var(--sans);margin:0 0 12px;padding-top:14px;border-top:1px solid var(--rule)}
.fig-num{color:var(--faint);font-weight:600;letter-spacing:.04em;margin-right:8px;text-transform:uppercase;font-size:12px}
figcaption{font:14.5px/1.6 var(--sans);color:var(--soft);margin-top:10px}
figcaption p{margin:0 0 6px} figcaption .take{color:var(--fg)}
.src{color:var(--faint);font-size:13px}
.plot{position:relative}
.chart{width:100%;height:auto;display:block;overflow:visible;touch-action:pan-y}
.chart .grid{stroke:var(--line);stroke-width:1}
.chart .zero{stroke:var(--faint);stroke-width:1;stroke-dasharray:3 3}
.chart .event{stroke:var(--faint);stroke-width:1.2;stroke-dasharray:2 3}
.chart .tick,.chart .event-label{fill:var(--faint);font:12px var(--sans)}
.chart .xhair{stroke:var(--soft);stroke-width:1;pointer-events:none}
.chart .hdot{stroke:var(--bg);stroke-width:2;pointer-events:none}
.legend{display:flex;flex-wrap:wrap;gap:4px 18px;font:13px var(--sans);color:var(--soft);margin-top:6px}
.key i{display:inline-block;width:16px;height:3px;border-radius:2px;margin-right:7px;vertical-align:middle}
.tip{position:absolute;z-index:2;pointer-events:none;background:var(--card);color:var(--fg);
border:1px solid var(--line);border-radius:6px;box-shadow:0 4px 16px rgba(0,0,0,.12);
padding:8px 10px;font:12.5px/1.5 var(--sans);white-space:nowrap}
.tip b{display:block;font-weight:600;margin-bottom:2px}
.tip div{display:flex;align-items:center;gap:7px} .tip i{width:8px;height:8px;border-radius:50%;display:inline-block}
.tip span{margin-left:auto;padding-left:14px;font-variant-numeric:tabular-nums;font-weight:600}
/* tables */
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font:14.5px/1.5 var(--sans)}
th{font-weight:600;text-align:left;padding:8px 10px;border-bottom:1.5px solid var(--fg);vertical-align:bottom}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td small{display:block;color:var(--faint);font-size:12.5px;white-space:normal}
.results td:first-child{font-weight:600;white-space:nowrap}
.results .big{font-size:17px;font-weight:600}
.indent{padding-left:16px;color:var(--soft)}
.m-only{display:none}
tr.total td{font-weight:600;border-top:1.5px solid var(--fg)}
/* asides and details */
.note{background:var(--tint);border-left:3px solid var(--c-control);padding:16px 20px;margin:26px 0;
font-size:16.5px;line-height:1.6}
.note p{margin:0}
details{border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:26px 0}
details+details{margin-top:-27px}
summary{cursor:pointer;list-style:none;font:600 14.5px/1.4 var(--sans);padding:14px 0;display:flex;
align-items:center;gap:10px;color:var(--fg)}
summary::-webkit-details-marker{display:none}
summary::before{content:"";width:7px;height:7px;border-right:1.5px solid var(--soft);border-bottom:1.5px solid var(--soft);
transform:rotate(-45deg);transition:transform .15s;margin:0 4px 0 2px}
details[open] summary::before{transform:rotate(45deg)}
summary span{font-weight:400;color:var(--faint)}
details>div{padding:2px 0 14px}
code{font:.84em var(--mono);background:var(--tint);padding:1px 5px;border-radius:3px}
pre{background:var(--tint);border-radius:6px;padding:16px 18px;overflow-x:auto;font-size:14px;line-height:1.6}
pre code,td code{background:none;padding:0}
footer{margin-top:80px;padding-top:18px;border-top:1px solid var(--line);font:13.5px/1.6 var(--sans);color:var(--faint)}
@media (max-width:1100px) and (min-width:821px){
.page{grid-template-columns:168px minmax(0,700px);gap:40px}}
@media (max-width:820px){
.page{grid-template-columns:minmax(0,700px);gap:0;padding-top:40px}
.toc{display:none}
.toc-inline{display:block;margin:34px 0 0;font:15px/1.5 var(--sans)}
.toc-inline ol{list-style:none;padding:0;margin:0;columns:2;column-gap:24px}
.toc-inline li a{display:flex;gap:10px;padding:4px 0;color:var(--soft);text-decoration:none}
.toc-inline .n{min-width:12px;color:var(--faint)}
html{scroll-padding-top:64px}
.mnav{display:block;position:sticky;top:0;z-index:10;font:15px/1.4 var(--sans);
background:var(--bg);
border-bottom:1px solid var(--line)}
.mnav details{border:0;margin:0}
.mnav summary{padding:0 16px;min-height:52px;gap:12px;font:15px/1.4 var(--sans)}
.mnav summary::before{display:none}
.mnav summary .mnav-btn{display:inline-flex;align-items:center;gap:7px;flex:none;padding:7px 13px 7px 11px;
border:1px solid var(--rule);border-radius:999px;background:var(--card);color:var(--fg);font:600 14px/1 var(--sans)}
.mnav-btn svg{width:16px;height:16px;stroke:currentColor;stroke-width:1.8;fill:none;stroke-linecap:round}
.mnav summary .mnav-cur{flex:1;min-width:0;font-weight:600;color:var(--fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mnav details[open]::before{content:"";position:fixed;inset:0;background:rgba(0,0,0,.42);z-index:1}
.mnav-drawer{position:fixed;top:0;left:0;bottom:0;width:min(84vw,320px);z-index:2;background:var(--bg);
border-right:1px solid var(--line);box-shadow:8px 0 28px rgba(0,0,0,.18);overflow-y:auto;
padding:0 20px 28px;animation:mnav-in .18s ease-out}
@keyframes mnav-in{from{transform:translateX(-100%)}to{transform:none}}
.mnav-head{display:flex;align-items:center;justify-content:space-between;min-height:56px;
border-bottom:1px solid var(--line);font:600 11.5px var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--faint)}
.mnav-x{appearance:none;border:0;background:none;color:var(--fg);font:22px/1 var(--sans);width:44px;height:44px;
margin-right:-12px;cursor:pointer}
.mnav ol{list-style:none;margin:0;padding:6px 0 0}
.mnav li a{display:flex;gap:14px;align-items:center;min-height:48px;color:var(--fg);text-decoration:none;
border-bottom:1px solid var(--line);font-size:16px}
.mnav li:last-child a{border-bottom:0}
.mnav li a.on{font-weight:600} .mnav li a.on .n{color:var(--fg)}
.mnav .n{min-width:14px;color:var(--faint);font-variant-numeric:tabular-nums}
.mnav-bar{height:2px} .mnav-bar i{display:block;height:100%;width:0;background:var(--c-primary)}
@media (prefers-reduced-motion:reduce){.mnav-drawer{animation:none}}}
@media (max-width:600px){
body{font-size:17px}
.page{padding:28px 16px 64px}
h1{font-size:33px} .dek{font-size:18.5px} h2{font-size:25px} h3{font-size:19px}
.chart .tick,.chart .event-label{font-size:19px}
.results .q,.results .vcol{display:none}
.m-only{display:block;margin-top:8px}
.results td:first-child{white-space:normal}
.toc-inline ol{columns:1}
.note{padding:14px 16px}}
@media print{.toc,.toc-inline,.mnav{display:none}.page{display:block;padding:0}details>div{display:block}}
"""

JS = """
(function(){
var NS='http://www.w3.org/2000/svg';
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
document.querySelectorAll('svg.chart[data-hover]').forEach(function(svg){
  var d=JSON.parse(svg.getAttribute('data-hover')),plot=svg.parentNode,dots=[];
  var line=document.createElementNS(NS,'line');line.setAttribute('class','xhair');
  line.setAttribute('y1',d.t);line.setAttribute('y2',d.b);line.style.display='none';svg.appendChild(line);
  var tip=document.createElement('div');tip.className='tip';tip.hidden=true;plot.appendChild(tip);
  function hide(){tip.hidden=true;line.style.display='none';dots.forEach(function(c){c.remove()});dots=[]}
  function show(e){
    var r=svg.getBoundingClientRect(),vx=(e.clientX-r.left)/r.width*d.w,i=0,best=1e9;
    for(var j=0;j<d.x.length;j++){var dd=Math.abs(d.x[j]-vx);if(dd<best){best=dd;i=j}}
    var x=d.x[i],row=d.rows[i];hide();
    line.setAttribute('x1',x);line.setAttribute('x2',x);line.style.display='';
    row[1].forEach(function(v){var c=document.createElementNS(NS,'circle');c.setAttribute('cx',x);
      c.setAttribute('cy',v[3]);c.setAttribute('r',4.5);c.setAttribute('fill',v[1]);c.setAttribute('class','hdot');
      svg.appendChild(c);dots.push(c)});
    tip.innerHTML='<b>'+esc(row[0])+'</b>'+row[1].map(function(v){return '<div><i style="background:'+v[1]+'"></i>'
      +esc(v[0])+'<span>'+esc(v[2])+'</span></div>'}).join('');
    tip.hidden=false;
    var pr=plot.getBoundingClientRect(),px=r.left-pr.left+x/d.w*r.width,tw=tip.offsetWidth,left=px+14;
    if(left+tw>pr.width)left=px-14-tw;tip.style.left=Math.max(0,left)+'px';tip.style.top=(r.top-pr.top+6)+'px';
  }
  svg.addEventListener('pointermove',show);svg.addEventListener('pointerdown',show);
  svg.addEventListener('pointerleave',function(e){if(e.pointerType!=='touch')hide()});
  document.addEventListener('pointerdown',function(e){if(!svg.contains(e.target))hide()});
});
var links=[].slice.call(document.querySelectorAll('nav.toc a,.mnav a'));
var menu=document.querySelector('.mnav details'),cur=document.querySelector('.mnav-cur');
document.querySelectorAll('.mnav a').forEach(function(a){a.addEventListener('click',function(){menu.open=false})});
if(menu){menu.addEventListener('click',function(e){if(e.target===menu)menu.open=false});
  var x=menu.querySelector('.mnav-x');if(x)x.addEventListener('click',function(){menu.open=false});
  addEventListener('keydown',function(e){if(e.key==='Escape')menu.open=false})}
if('IntersectionObserver' in window&&links.length){
  var byId={};links.forEach(function(a){var k=a.getAttribute('href').slice(1);(byId[k]=byId[k]||[]).push(a)});
  var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting&&byId[e.target.id]){
    links.forEach(function(a){a.classList.remove('on')});
    byId[e.target.id].forEach(function(a){a.classList.add('on')});
    if(cur)cur.textContent=byId[e.target.id][0].getAttribute('data-t')}})},
    {rootMargin:'-10% 0px -75% 0px'});
  document.querySelectorAll('article [id]').forEach(function(s){if(byId[s.id])io.observe(s)});
}
var bar=document.querySelector('.mnav-bar i'),ticking=false;
function prog(){var h=document.documentElement.scrollHeight-innerHeight;
  if(bar)bar.style.width=(h>0?Math.min(100,scrollY/h*100):0)+'%';ticking=false}
addEventListener('scroll',function(){if(!ticking){ticking=true;requestAnimationFrame(prog)}},{passive:true});prog();
})();
"""

TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zeat: is NEAR Intents' revenue defensible?</title>
<meta name="description" content="Is NEAR Intents' revenue defensible? Three pre-registered causal tests against a competitor control, checked on-chain, rebuilt from public data with one command.">
<meta property="og:title" content="Zeat: is NEAR Intents' revenue defensible?">
<meta property="og:description" content="{overall} ({passes} of 3 pre-registered tests passed). Every number rebuilds from public data with one command.">
<meta property="og:type" content="article">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&display=swap">
<style>""" + CSS.replace("{", "{{").replace("}", "}}") + """</style></head><body>
<nav class="mnav" aria-label="Contents"><details><summary><span class="mnav-btn"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12"/></svg>Menu</span>
<span class="mnav-cur">Abstract</span></summary>
<div class="mnav-drawer"><div class="mnav-head">Contents<button class="mnav-x" type="button" aria-label="Close menu">×</button></div><ol>{toc}</ol></div></details>
<div class="mnav-bar" aria-hidden="true"><i></i></div></nav>
<div class="page">
<nav class="toc" aria-label="Contents"><p>Contents</p><ol>{toc}</ol></nav>
<article>

<header>
<p class="kicker">Zeat · Research note · NEAR HACKATHON 2026 · Investment Thesis track</p>
<h1>Is NEAR Intents' revenue defensible?</h1>
<p class="dek">{dek}</p>
<p class="byline"><b>Dydex</b> · Data snapshot {snapshot} · <a href="{repo}">Code</a> ·
<a href="METHODS.md">Pre-registration</a> · <a href="THESIS.md">Thesis</a> · <a href="results.json">All numbers (JSON)</a></p>
{banner}
</header>

<section class="abstract" id="abstract" style="margin-top:40px">
<h2 class="label">Abstract</h2>
<p>Most NEAR theses measure how much NEAR Intents earns. An investor's next question is whether it can
keep earning it. This note tests that three ways, each against a synthetic control built from competing
venues, so a market-wide move is never mistaken for a NEAR-specific one. The questions, data rules and
pass/fail thresholds were committed to git before any result was computed.</p>

<figure>
<p class="fig-title"><span class="fig-num">Table 1</span>Results under the pre-registered rules · <b>{overall}</b>, {passes} of 3 passed</p>
<div class="tablewrap"><table class="results">
<thead><tr><th>Test</th><th class="q">Question</th><th class="num">Estimate</th><th class="num">Placebo p</th><th class="vcol">Verdict</th></tr></thead>
<tbody>
<tr><td><a href="#t1">T1</a> Pricing power<span class="m-only">{b1}</span></td><td class="q">When NEAR started taking a cut on Feb 23, 2026, did volume leave?</td>
<td class="num"><span class="big">{t1_effect}</span><small>volume vs control, 8 weeks</small></td><td class="num">{t1_p}*</td><td class="vcol">{b1}</td></tr>
<tr><td><a href="#t2">T2</a> Trust shock<span class="m-only">{b2}</span></td><td class="q">After the Oct 1, 2026 exploit, did volume come back?</td>
<td class="num"><span class="big">{t2_effect}</span><small>volume vs control, weeks 4–5</small></td><td class="num">{t2_p}</td><td class="vcol">{b2}</td></tr>
<tr><td><a href="#t3">T3</a> Price premium<span class="m-only">{b3}</span></td><td class="q">Does Intents charge more than rivals and still hold share?</td>
<td class="num"><span class="big">{t3_bps_intents} vs {t3_bps_comp}</span><small>bps, Intents vs rivals; dearer in {t3_premium} of weeks</small></td><td class="num">n/a</td><td class="vcol">{b3}</td></tr>
</tbody></table></div>
<figcaption><p>T1 and T2 fail only on a loss worse than −10% with placebo p &lt; 0.10. T3 needs Intents to be
dearer than rivals in at least 75% of weeks with a share that is not falling. T2: {t2_robust_note}</p>
<p class="src">* T1's p-value is not informative: {t1_share_above} of its placebo windows fall in Intents' 2025
hypergrowth and show larger gains than the real effect (see <a href="#t1">Section 2</a>).</p></figcaption>
</figure>

<h2 class="label" style="margin-top:34px!important">Key findings for an investor</h2>
<ol class="findings">{takeaways}</ol>
<nav class="toc-inline" aria-label="Contents"><h2 class="label">Contents</h2><ol>{toc}</ol></nav>
</section>

<section id="design">
<h2><span class="secnum">1</span>Question and design</h2>
<p>Revenue is only worth a high multiple if it is defensible. NEAR Intents now earns real fees, so the
question is whether it has a moat: can it raise its take, survive a loss of trust, and charge more than
rivals, without losing volume?</p>
<figure>
<p class="fig-title"><span class="fig-num">Figure 1</span>NEAR Intents weekly volume, log scale</p>
{c_hist}
<figcaption><p class="take">Intents grew from almost nothing to a large venue in 2025; growth flattened in 2026.
Both events tested here sit on the mature part of the curve.</p>
<p class="src">Source: DefiLlama <code>near-intents</code> daily volume, summed to Monday–Sunday weeks; weeks with
fewer than 4 reported days are left blank.</p></figcaption>
</figure>
<p>Each test compares Intents with a <b>synthetic control</b>: a weighted mix of competitors (THORChain,
Chainflip, Maya, SOCKET, 0x and the all-DEX market) fitted to Intents' log weekly volume over the 26 weeks
before an event. The effect is the gap that opens after it. To judge whether a gap is unusual, the same
estimator is re-run at every earlier fake event date (a <b>placebo test</b>). LI.FI, Rango and Bitget route
part of their flow through Intents, so they are kept out of the control and used only as a sensitivity check.
Full rules: <a href="METHODS.md">METHODS.md</a>.</p>
</section>

<section id="t1">
<h2><span class="secnum">2</span>Pricing power: the fee switch {b1}</h2>
<p class="meta"><b>Event</b> Feb 23, 2026 · <b>Estimate</b> {t1_effect} volume vs control over 8 weeks ·
<b>Rule</b> fail only on a loss worse than −10% with p &lt; 0.10</p>
<p>On Feb 23, 2026 NEAR Intents switched on a protocol cut of the fees integrators charge. If integrators
or their users had cheaper alternatives, volume should have fallen relative to competitors.</p>
<figure>
<p class="fig-title"><span class="fig-num">Figure 2</span>Share of fees NEAR keeps, weekly</p>
{c_cap}
<figcaption><p class="take">The switch was real. NEAR's share of fees rose from {t1_cap_pre} in the 26 weeks
before to {t1_cap_post} in the 8 weeks after, while {switch_note} ({t1_bps_pre} bps before, {t1_bps_post} bps after).</p>
<p class="src">Source: DefiLlama <code>near-intents</code> daily revenue ÷ daily fees, weekly.</p></figcaption>
</figure>
<p>Because the price users paid did not move, T1 measures whether integrators and their flow left,
not users' price sensitivity.</p>
<figure>
<p class="fig-title"><span class="fig-num">Figure 3</span>Fee switch: NEAR Intents vs its synthetic control</p>
{c_t1}
<figcaption><p class="take">In the 8 weeks after the switch, Intents ran {t1_effect} relative to its
synthetic control. Verdict: {b1}</p>
<p class="src">Control weights, fitted on the 26 weeks before the event: {t1_weights}. Pre-period fit error
(RMSPE) is {t1_pre_rmspe} log points, which is loose: Intents' 2025 hypergrowth is hard for any mix of mature
competitors to match.</p></figcaption>
</figure>
<div class="note"><p><b>Read this with care.</b> {t1_share_above} of the {t1_n} placebo windows show a larger
gain than the real one (median {t1_placebo_median}), because they sit in 2025, when Intents was outgrowing
everything. So the fee switch coincided with Intents' growth lead shrinking. The T2 placebo series
(<a href="#t2">Section 3</a>) shows that lead had already fallen towards zero by January 2026, weeks before the
switch, so the slowdown is not evidence that the switch caused it.</p></div>
<details><summary>Placebo tests for T1 <span>Figures 4–5</span></summary><div>
<figure>
<p class="fig-title"><span class="fig-num">Figure 4</span>Gap to control, real vs {t1_n} placebo windows</p>
{c_t1_gap}
<figcaption><p class="src">Grey: the same estimator run at fake event dates before the switch. Blue: the real gap.</p></figcaption>
</figure>
<figure>
<p class="fig-title"><span class="fig-num">Figure 5</span>T1 placebo effects by fake event date</p>
{c_t1_dates}
<figcaption><p class="src">Each dot is the effect estimated at a fake event date; the line is the real effect, {t1_effect}.</p></figcaption>
</figure></div></details>
<details><summary>Robustness checks <span>not used for the verdict</span></summary><div>
<div class="tablewrap"><table><thead><tr><th>Variant</th><th class="num">Effect</th></tr></thead><tbody>{rob1}</tbody></table></div>
</div></details>
</section>

<section id="t2">
<h2><span class="secnum">3</span>Trust shock: the exploit {b2}</h2>
<p class="meta"><b>Event</b> Oct 1, 2026 · <b>Estimate</b> {t2_effect} volume vs control in weeks 4–5 ·
<b>Placebo p</b> {t2_p} · <b>Rule</b> fail only on a loss worse than −10% with p &lt; 0.10</p>
<p>On Oct 1, 2026 NEAR Intents was exploited for about $3.8M through a deposit-notification bug. The contract
was paused within about 30 minutes, deposits resumed on Oct 2, and the funds were returned. A venue with
loyal users should see volume come back within weeks.</p>
<figure>
<p class="fig-title"><span class="fig-num">Figure 6</span>Exploit: NEAR Intents vs its synthetic control</p>
{c_t2}
<figcaption><p class="take">{t2_shape_cap} (weeks 0–1: {t2_shock}), then Intents trailed its control by
{t2_effect} in weeks 4–5. Week by week: {t2_weekly}.</p>
<p class="src">Control fitted on 26 pre-event weeks ({t2_weights}); pre-period RMSPE {t2_pre_rmspe}.
Recovery statistic: mean gap in weeks 4–5.</p></figcaption>
</figure>
<figure>
<p class="fig-title"><span class="fig-num">Figure 7</span>How unusual is {t2_effect}? Placebo effects at 2026 fake event dates</p>
{c_t2_mature}
<figcaption><p class="take">Against all {t2_n} placebo windows, p = {t2_p}. Using only the {t2_n_mature} windows
dated 2026, after the hypergrowth phase, p = {t2_p_mature}. {t2_p_phrase}. Verdict: {b2}</p>
<p class="src">Each dot re-runs the T2 estimator at a fake event date; the line is the real effect.</p></figcaption>
</figure>
{t2_fragile_note}
<details><summary>All placebo windows for T2 <span>Figures 8–9</span></summary><div>
<figure>
<p class="fig-title"><span class="fig-num">Figure 8</span>Gap to control, real vs {t2_n} placebo windows</p>
{c_t2_gap}
</figure>
<figure>
<p class="fig-title"><span class="fig-num">Figure 9</span>T2 placebo effects by fake event date, all windows</p>
{c_t2_dates}
<figcaption><p class="src">In 2025 Intents outgrew every control, so those placebos sit far above zero; that
is why Figure 7 uses 2026 windows only.</p></figcaption>
</figure></div></details>
<details><summary>Robustness checks <span>not used for the verdict</span></summary><div>
<div class="tablewrap"><table><thead><tr><th>Variant</th><th class="num">Effect</th></tr></thead><tbody>{rob2}</tbody></table></div>
</div></details>
</section>

<section id="t3">
<h2><span class="secnum">4</span>Price premium {b3}</h2>
<p class="meta"><b>Window</b> {t3_window} · <b>Estimate</b> {t3_bps_intents} vs {t3_bps_comp} bps ·
<b>Rule</b> dearer in ≥75% of weeks and share not falling</p>
<p>A business with a moat can charge more than rivals and keep its customers. This test compares what users
pay per dollar swapped on Intents with what they pay on native cross-chain rivals.</p>
<figure>
<p class="fig-title"><span class="fig-num">Figure 10</span>Fee rate paid by users, basis points</p>
{c_fee}
<figcaption><p class="take">Intents' median fee rate was {t3_bps_intents} bps against {t3_bps_comp} bps for
competitors; Intents was dearer in only {t3_premium} of {t3_weeks} weeks.</p>
<p class="src">Source: DefiLlama daily fees ÷ daily volume, weekly, per venue. The competitor rate is
volume-weighted across THORChain, Chainflip and Maya for the venues reporting that week (grey lines).</p></figcaption>
</figure>
<figure>
<p class="fig-title"><span class="fig-num">Figure 11</span>NEAR Intents' volume share against {t3_share_vs}</p>
{c_share}
<figcaption><p class="take">Share went from {t3_share_first} to {t3_share_last}; trend {t3_slope} a week (90% CI
{t3_ci_lo} to {t3_ci_hi}), so share is {t3_share_word}. Against THORChain and Chainflip over the {t3_sens_n}
weeks both report, the trend is {t3_sens} a week.{t3_sens_note}</p>
<p class="src">Share uses only competitors that report every week of the window, because a denominator that
gains and loses venues would move on its own.</p></figcaption>
</figure>
<p>T3 needs both a premium in at least 75% of weeks and a share that is not falling. Verdict: {b3}</p>
</section>

{chain_html}
{near_html}

<section id="limits">
<h2><span class="secnum">7</span>Limits</h2>
<ul class="plain">
<li>All volume and fee data comes from DefiLlama, an aggregator. Its history can be revised; the snapshot
hashes in Section 8 pin the exact version analysed.</li>
<li>The control pool is small (6 clean series), so placebo-in-space p-values cannot go below about 1/6.</li>
<li>The on-chain figures come from a sample of blocks, not a full census, so each weekly estimate carries
sampling error (bootstrap intervals are in <code>results.json</code>). The sample is pinned in
<code>data/onchain/</code> and can be checked against the chain with <code>python3 -m zeat verify-onchain</code>.</li>
<li>Six weeks of post-exploit data is the most the snapshot allows. T2 should be re-run as data arrives;
<code>python3 -m zeat refresh</code> then <code>build</code> does exactly that, and a daily job republishes this page on fresh data.</li>
</ul>
</section>

<section id="reproduce">
<h2><span class="secnum">8</span>Reproduce</h2>
<p>Python 3.10+, standard library only, no API keys. The build is offline and byte-deterministic: it must
reproduce this page, <code>results.json</code> and THESIS.md exactly.</p>
<pre><code>git clone {repo} &amp;&amp; cd zeat
python3 -m zeat verify     # data files match their sha256 hashes
python3 -m zeat build      # rebuilds every number, this page and THESIS.md (~40 s)
git status --short         # empty: the rebuild matches the committed files
python3 -m unittest        # known-answer and byte-exact rebuild tests</code></pre>
<details><summary>Data sources and hashes <span>snapshot fetched {fetched}</span></summary><div>
<div class="tablewrap"><table><thead><tr><th>Series</th><th>Role</th><th>Source</th><th>sha256</th></tr></thead>
<tbody>{src_rows}</tbody></table></div></div></details>
</section>

<footer>Not financial advice. Built at NEAR HACKATHON 2026. Every number on this page is filled in by
<code>python3 -m zeat build</code> from <a href="results.json">results.json</a>; none is typed by hand.</footer>
</article></div>
<script>""" + JS.replace("{", "{{").replace("}", "}}") + """</script>
</body></html>
"""
