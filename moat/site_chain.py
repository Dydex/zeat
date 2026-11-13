"""Dashboard sections for the on-chain sample and the NEAR-level economics."""

import datetime as dt
import html
import math

from . import charts

D = dt.date
EXPLOIT = D(2026, 10, 1)


def sections(res, f, ordinal, month_label):
    c = res.get("chain")
    if not c or not f.get("has_chain"):
        return "", ""
    e = html.escape
    v = c["validation"]["intents_executed"]["pairs"]
    c_val = ""
    if v:
        b0 = sum(p["log_onchain"] for p in v[:8]) / len(v[:8])
        b1 = sum(p["log_defillama"] for p in v[:8]) / len(v[:8])
        xs = lambda p: ordinal(D.fromisoformat(p["week_start"]))
        c_val = charts.line_chart(
            [dict(name="On-chain: intents executed (block sample)", style="accent", width=2.4,
                  points=[(xs(p), math.exp(p["log_onchain"] - b0)) for p in v]),
             dict(name="DefiLlama: Intents volume", style="primary", width=2.4, dash="6 4",
                  points=[(xs(p), math.exp(p["log_defillama"] - b1)) for p in v])],
            title="On-chain activity vs DefiLlama volume",
            desc="Both series indexed to their mean over the first 8 weeks, log scale.",
            x_fmt=month_label, y_fmt=lambda y: f"{y:.1f}×", log_y=True,
            vlines=[(ordinal(EXPLOIT), "exploit")])
    pz = c["pause"]
    c_pause = ""
    if pz:
        t0 = pz["points"][0]["ts"]
        c_pause = charts.line_chart(
            [dict(name="intents.near receipts in the sampled block", style="accent", width=1.8,
                  points=[((p["ts"] - t0) / 3.6e6, p["receipts"]) for p in pz["points"]])],
            title="One block sampled every 30 minutes, Sep 30 to Oct 2",
            desc="Successful intents.near receipts in one block sampled every 30 minutes.",
            x_fmt=lambda hrs: (dt.datetime.fromtimestamp(t0 / 1000 + hrs * 3600, dt.timezone.utc)
                               .strftime("%b %d %H:%M")),
            y_fmt=lambda y: f"{y:g}", x_ticks=list(range(0, 73, 12)), hline=0)
    sv = c["solvers"]
    solver_rows = "".join(
        f"<tr><td><code>{e(r['account'][:30] + ('…' if len(r['account']) > 30 else ''))}</code></td>"
        f"<td class='num'>{r['share']:.1%}</td></tr>" for r in (sv["top"] if sv else []))
    chain_html = CHAIN.format(c_val=c_val, c_pause=c_pause, solver_rows=solver_rows,
                              **{k: f.get(k, "n/a") for k in KEYS})
    near_html = NEAR.format(**{k: f.get(k, "n/a") for k in KEYS}) if c.get("economics") else ""
    return chain_html, near_html


KEYS = ["fs_chain", "fs_llama", "fs_val_r_changes", "blocks", "val_agree", "val_weeks", "val_r_levels", "val_r_changes", "ex_agree", "ex_chain",
        "ex_llama", "pz_note", "pz_samples", "pz_base", "pz_run", "pz_hours", "pz_from", "pz_to", "sv_n",
        "sv_top1", "sv_top3", "sv_hhi", "sv_level", "issued", "supply_growth", "price",
        "issuance_usd", "rev_annual", "coverage", "capture_now", "needed_capture", "needed_vol",
        "capture_lever", "fee_bps_now"]

CHAIN = """
<h2>On-chain check: reading NEAR blocks directly</h2>
<p>Every test above uses DefiLlama, an aggregator. To check it against the chain itself, the build
reads a deterministic sample of {blocks} NEAR blocks from <code>neardata.xyz</code> (keyless) and counts
what <code>intents.near</code> executed in each one: signed intents (<code>intents_executed</code>
events), swaps (<code>token_diff</code> events) and receipts. A weekly total is the mean per sampled
block times the number of blocks in that week.</p>
{c_val}
<p class="shows"><b>What it shows:</b> DefiLlama's volume {val_agree} on-chain activity. Across {val_weeks}
weeks the correlation is {val_r_levels} in levels and {val_r_changes} in week-to-week changes; the second
is the stricter test.</p>
<p class="how">Volume is dollars and on-chain counts are actions, so they need not move one-for-one. A
low correlation in changes would mean the aggregator's weekly swings are not visible on-chain.</p>

<h3>The fee switch, on-chain</h3>
<p class="shows">Executed intents in the 8 weeks after Feb 23 were {fs_chain} against the 8 weeks before;
DefiLlama volume was {fs_llama}. In this window the week-to-week correlation of the two is {fs_val_r_changes}.</p>

<h3>The exploit, on-chain</h3>
<p class="shows">{ex_agree}: executed intents in weeks 4–5 after Oct 1 were {ex_chain} against the 8 weeks
before, while DefiLlama volume was {ex_llama} over the same weeks. This is a before/after comparison with no
competitor control, because competitors' activity lives on other chains, so it is not comparable with T2's
synthetic-control gap: both raw measures can rise while Intents still loses ground to rivals. Counts of signed
intents are not dollars, and one strong week (Nov 5–11) drives most of the on-chain rise.</p>
{c_pause}
<p class="shows"><b>What it shows:</b> across {pz_samples} blocks sampled every 30 minutes, a typical block
before Oct 1 carried {pz_base} intents receipts. The longest run of sampled blocks with none was {pz_run}
(about {pz_hours} hours), from {pz_from} to {pz_to}. {pz_note}</p>

<h3>Who fills the swaps?</h3>
<p>Each swap settles as a <code>token_diff</code> between a user and a solver. Users rarely appear in more
than one sampled block; solvers do. Over the last 8 weeks, {sv_n} accounts appeared in swaps in at least
3 different sampled blocks. Their shares of those appearances:</p>
<div class="tablewrap"><table><thead><tr><th>Repeat counterparty</th><th class="num">Share</th></tr></thead>
<tbody>{solver_rows}</tbody></table></div>
<p class="shows"><b>What it shows:</b> the top solver-side account carries {sv_top1}, the top 3 carry {sv_top3}
(HHI {sv_hhi}): {sv_level}. A concentrated solver set is a single point of failure for price and
uptime, which matters for the trust result in T2.</p>
<p class="how">Descriptive. An account that routes on behalf of many users can look like a solver, so this
measures repeat counterparties, not confirmed solvers.</p>
"""

NEAR = """
<h2>The long-term case for NEAR</h2>
<p>NEAR holders are diluted by new issuance; Intents revenue is what can offset it. Revenue is
volume × fee rate × NEAR's cut, and the three tests say which of those levers NEAR can pull.</p>
<div class="tablewrap"><table><tbody>
<tr><td>NEAR issued in the last year, from block headers</td><td class="num">{issued} NEAR ({supply_growth})</td></tr>
<tr><td>Value of that issuance at the 30-day average price ({price})</td><td class="num">{issuance_usd} a year</td></tr>
<tr><td>Intents protocol revenue, trailing 12 weeks annualised</td><td class="num">{rev_annual} a year</td></tr>
<tr><td><b>Revenue as a share of issuance value</b></td><td class="num"><b>{coverage}</b></td></tr>
<tr><td>NEAR's cut of Intents fees, trailing 12 weeks</td><td class="num">{capture_now}</td></tr>
<tr><td>Cut needed to cover issuance at today's volume and fee rate</td><td class="num">{needed_capture}</td></tr>
<tr><td>Volume growth needed at today's cut and fee rate</td><td class="num">{needed_vol}</td></tr>
</tbody></table></div>
<div class="tablewrap"><table><thead><tr><th>Lever</th><th>What the moat tests say</th></tr></thead><tbody>
<tr><td>NEAR's cut ({capture_now} now)</td><td>T1: raising it did not cost volume. This is the proven lever, but it {capture_lever}.</td></tr>
<tr><td>Fee rate ({fee_bps_now} bps)</td><td>T3: Intents is already cheaper than rivals and has no premium to spend; raising it is untested.</td></tr>
<tr><td>Volume</td><td>T2: volume is the lever exposed to trust. Growth of {needed_vol} has to come from users who stay through incidents.</td></tr>
</tbody></table></div>
<p class="how">Issuance is the exact change in <code>total_supply</code> between two block headers a year apart
(net of burns). Price is CoinGecko's 30-day average before the snapshot. Revenue is DefiLlama's. Covering issuance
is a yardstick for value accrual, not a claim about how buybacks are executed.</p>
"""
