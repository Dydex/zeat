"""Formatted numbers shared by the dashboard and THESIS.md.

Prose never contains a hand-typed number: everything quoted comes from here,
and everything here comes from the analysis results.
"""

import datetime as dt


def spct(x, nd=0):
    return "n/a" if x is None else f"{x * 100:+.{nd}f}%"


def upct(x, nd=0):
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def pval(p):
    return "n/a" if p is None else f"{p:.2f}"


def nice_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def facts(res):
    t1, t2, t3 = (res["tests"][k] for k in ("t1", "t2", "t3"))
    fs = t1["first_stage"]
    pd1, pd2 = t1["placebo_distribution"], t2["placebo_distribution"]
    r1, r2 = t1["robustness"], t2["robustness"]
    return dict(
        snapshot=nice_date(res["snapshot_date"]),
        overall=res["overall"], passes=res["passes"],
        # T1
        t1_verdict=t1["verdict"], t1_effect=spct(t1["effect_pct"]),
        t1_p=pval(t1["p_loss"]), t1_n=t1["n_placebos"],
        t1_placebo_median=spct(pd1["median_pct"]), t1_placebo_min=spct(pd1["min_pct"]),
        t1_cap_pre=upct(fs["pre"]["capture"], 1), t1_cap_post=upct(fs["post"]["capture"], 1),
        t1_bps_pre=f"{fs['pre']['fee_bps']:.1f}", t1_bps_post=f"{fs['post']['fee_bps']:.1f}",
        t1_loo_lo=spct(r1["leave_one_out_range_pct"][0]), t1_loo_hi=spct(r1["leave_one_out_range_pct"][1]),
        t1_did=spct(r1["did_pct"]), t1_pre13=spct(r1["pre_13_weeks_pct"]),
        t1_contam=spct(r1["with_contaminated_pct"]),
        t1_pre_rmspe=f"{t1['fit']['pre_rmspe']:.2f}",
        t1_weights=", ".join(f"{k} {v:.0%}" for k, v in t1["fit"]["weights"].items()),
        # T2
        t2_verdict=t2["verdict"], t2_effect=spct(t2["effect_pct"]),
        t2_shock=spct(t2["shock_pct"]), t2_p=pval(t2["p_loss"]), t2_n=t2["n_placebos"],
        t2_p_mature=pval(pd2["p_loss_mature"]), t2_n_mature=pd2["n_mature"],
        t2_placebo_median=spct(pd2["median_pct"]),
        t2_loo_lo=spct(r2["leave_one_out_range_pct"][0]), t2_loo_hi=spct(r2["leave_one_out_range_pct"][1]),
        t2_did=spct(r2["did_pct"]), t2_pre13=spct(r2["pre_13_weeks_pct"]),
        t2_contam=spct(r2["with_contaminated_pct"]),
        t2_pre_rmspe=f"{t2['fit']['pre_rmspe']:.2f}",
        t2_weights=", ".join(f"{k} {v:.0%}" for k, v in t2["fit"]["weights"].items()),
        t2_space_rank=t2["placebo_in_space"]["rank"], t2_space_n=t2["placebo_in_space"]["n"],
        t2_weekly=", ".join(f"wk {k}: {spct(v)}" for k, v in t2["weekly_gap_pct"].items()),
        # T3
        t3_verdict=t3["verdict"], t3_premium=upct(t3["premium_weeks"]),
        t3_weeks=t3["weeks_rated"],
        t3_bps_intents=f"{t3['median_intents_bps']:.1f}", t3_bps_comp=f"{t3['median_competitor_bps']:.1f}",
        t3_share_first=upct(t3["share_first"]), t3_share_last=upct(t3["share_last"]),
        t3_slope=spct(t3["share_slope_pct_per_week"], 2),
        t3_ci_lo=spct(t3["share_slope_ci90"][0], 2), t3_ci_hi=spct(t3["share_slope_ci90"][1], 2),
        t3_sens=spct(t3["sensitivity_share_slope_thor_chainflip"], 2), t3_sens_n=t3["sensitivity_weeks"],
        t3_elast=f"{t3['elasticity_descriptive']:.2f}",
        t3_window=f"{nice_date(t3['window_start'])} to {nice_date(t3['window_end'])}",
        t3_share_vs=", ".join(t3["share_competitors"]),
        t1_share_above=upct(1 - t1["p_loss"]),
        **phrases(res),
    )


def phrases(res):
    """Sentences whose wording depends on the results, so a refresh can't leave
    the prose saying something the numbers no longer support."""
    t1, t2, t3 = (res["tests"][k] for k in ("t1", "t2", "t3"))
    fs = t1["first_stage"]
    cap_up = fs["post"]["capture"] > fs["pre"]["capture"]
    price_flat = abs(fs["post"]["fee_bps"] / fs["pre"]["fee_bps"] - 1) < 0.10
    lo, hi = t3["share_slope_ci90"]

    if t1["verdict"] == "PASS":
        k1 = ("<b>The fee switch did not cost volume.</b> " +
              ("NEAR raised its share of fees and " if cap_up else "") +
              "volume kept pace with competitors. Taking a cut has not driven integrators away, so far.")
    else:
        k1 = ("<b>The fee switch cost volume.</b> After NEAR began taking a cut, volume fell "
              "significantly behind competitors.")
    cheaper = t3["median_intents_bps"] < t3["median_competitor_bps"]
    if cheaper:
        k2 = ("<b>Intents is the cheaper venue, not the premium one.</b> Its users pay less than on "
              "native cross-chain rivals. That is a growth strategy, not evidence of a moat: a cheaper "
              "rival could compete the same way.")
    else:
        k2 = ("<b>Intents charges more than its rivals</b>" +
              (" and still holds share: evidence of pricing power." if hi >= 0 else
               ", but is losing share."))
    lo2, hi2 = t2["robustness"]["leave_one_out_range_pct"]
    fragile = lo2 < 0 < hi2
    if t2["verdict"] == "FAIL":
        k3 = ("<b>Trust is the open risk.</b> Volume trailed its control by weeks 4–5 after the exploit. " +
              ("The signal passes the pre-registered test but is fragile under robustness checks; "
               "it is the number to watch." if fragile else
               "The result holds when any single control is dropped."))
    else:
        k3 = ("<b>Users came back after the exploit.</b> By weeks 4–5 volume was not significantly "
              "behind its control.")
    sens = t3["sensitivity_share_slope_thor_chainflip"]
    sens_note = ""
    if sens is not None and sens < -0.005:
        sens_note = (" That broader comparison points to share slipping against the larger rival, "
                     "so “holding” applies to Chainflip only.")
    space = t2["placebo_in_space"]
    fragile_note = ""
    if fragile:
        fragile_note = (
            f"<div class=\"note\"><p><b>Why this is fragile.</b> Dropping a single control moves the "
            f"estimate between {spct(lo2)} and {spct(hi2)}. Adding the contaminated aggregators gives "
            f"{spct(t2['robustness']['with_contaminated_pct'])}. In the placebo-in-space test, Intents' "
            f"post-event deviation ranks {space['rank']} of {space['n']}"
            + (": less unusual than its own controls'." if space["rank"] == space["n"] else ".")
            + (" And the shape is not a typical trust shock: there was no drop in the first two weeks."
               if t2["shock_pct"] > -0.10 else "")
            + " Treat this as a warning signal to re-test, not a settled loss.</p></div>")
    return dict(
        t3_sens_note=sens_note, t2_fragile_note=fragile_note,
        takeaways="".join(f"<li>{k}</li>" for k in (k1, k2, k3)),
        takeaways_md="\n".join("- " + k.replace("<b>", "**").replace("</b>", "**") for k in (k1, k2, k3)),
        t2_robust_note=("Not robust to the choice of controls." if fragile else "Robust to dropping any one control."),
        t2_shape=("no immediate collapse" if t2["shock_pct"] > -0.10 else "an immediate drop"),
        t3_share_word=("holding" if hi >= 0 and lo <= 0 else "rising" if lo > 0 else "falling"),
        switch_note=("the fee rate users paid stayed level" if price_flat else "the fee rate users paid changed"),
    )
