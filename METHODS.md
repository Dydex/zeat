# Methods (pre-registered)

This file fixes the questions, data rules, estimators and pass/fail thresholds
**before** the final analysis was run. It was committed to git ahead of the
analysis code and the results; `git log -- METHODS.md` shows the order. Any
later change to this file is listed in section 8, with its reason.

**Disclosure.** On 2026-11-12, before this file was written, the author did one
exploratory comparison: 30-day mean volume before and after 2026-02-26 for
NEAR Intents (−25%), THORChain (−24%), Chainflip (−43%) and Maya (−47%). No
other outcome was looked at before pre-registration.

## 1. Question

Revenue is only worth a high multiple if it is defensible. NEAR Intents now
earns real fees, so this project asks: **does NEAR Intents have a moat?** It is
measured three ways, each against a control built from competitors, so that
market-wide moves are not mistaken for NEAR-specific ones.

| Test | Event | Question | Moat signal |
|---|---|---|---|
| T1 Pricing power | Fee switch, 2026-02-23 (Mon) | When NEAR started taking a cut, did volume leave? | No significant loss vs control |
| T2 Trust shock | Exploit and pause, 2026-10-01 (Thu) | After a $3.8M exploit and pause, did volume come back? | Gap closed by weeks 4–5 |
| T3 Price premium | Last 26 complete weeks | Does Intents charge more than rivals and still hold share? | Premium in ≥75% of weeks, share not falling |

Event sources: the fee switch announcement by NEAR Intents
(<https://x.com/near_intents/status/2026016131589591090>) and the exploit
post-mortem coverage (<https://www.cryptotimes.io/2026/10/17/near-intents-traces-3-8m-exploit-to-smart-contract-deposit-bug/>).

## 2. Data

All data is public, keyless and listed in `moat/sources.py`. `refresh`
downloads it and records a sha256 per file in `data/manifest.json`. `build`
refuses to run on files that do not match their hashes.

- **Treated:** NEAR Intents daily volume (DefiLlama `near-intents`).
- **Clean donor pool (controls):** THORChain, Chainflip, Maya Protocol (native
  cross-chain swap venues); SOCKET and 0x bridge aggregators; all-DEX volume
  (the market). None is known to route its own flow through NEAR Intents.
- **Excluded from the donor pool, sensitivity only:** LI.FI, Rango and Bitget
  Wallet. Each routes part of its flow through NEAR Intents, so a shock to
  Intents also hits them and would bias the estimated effect toward zero.
- **Fees:** DefiLlama daily fees for Intents, THORChain, Chainflip and Maya.
- **Revenue:** DefiLlama daily revenue for Intents (the protocol's own take).

## 3. Cleaning rules

1. Snapshot date `S` is the UTC date of the fetch. Only days before `S` are used.
2. A daily value of zero is treated as missing (a reporting gap or a halt). It is
   never imputed.
3. **Event-weeks.** For event day `E`, week `k` covers days `E+7k … E+7k+6`.
   A week's value is `7 × mean(observed days)` if at least 4 of its 7 days are
   observed; otherwise the week is missing. Only complete calendar spans
   (all 7 days before `S`) are used.
4. All volume comparisons use natural logs of weekly volume.

## 4. Estimator: synthetic control with intercept

For an event `E`, a pre-window of `P = 26` weeks (`k = −26 … −1`) and a post
window of `H` weeks:

- A donor is eligible if it is observed in ≥ 80% of pre-weeks and in every
  post week.
- Weights `w ≥ 0, Σw = 1` minimise the pre-period squared error between the
  demeaned log volume of Intents and the demeaned weighted donors. The fit uses
  pre-weeks where every eligible donor is observed. The intercept is
  `mean(y_pre) − mean(X_pre)·w`, so the control matches trends, not levels.
- `gap_k = log y_k − (intercept + X_k·w)`. The **effect** is the mean gap over
  the chosen post weeks, reported as `exp(effect) − 1`.

### Inference

- **Placebo-in-time (primary).** The same estimator is run at fake event dates
  `E'`, every 7 days, whose whole window (pre and post) ends before `E` and
  starts on or after the first week Intents is observed. The one-sided p-value
  for a loss is the share of placebo effects ≤ the real effect. Placebo windows
  may contain other real events; this widens the placebo spread and so makes the
  test conservative.
- **Placebo-in-space (secondary).** Each eligible donor is treated as if it had
  the event, using the other donors (not Intents) as controls. Intents' rank by
  post/pre RMSPE ratio is reported. With few donors this is weak, and the report
  says so.

### Robustness (reported, not used for verdicts)

- Leave-one-donor-out: the range of effects.
- Simple difference-in-differences: change in `log y − mean(log donors)`.
- Pre-window of 13 weeks instead of 26.
- Contaminated donors added to the pool.

## 5. Tests and decision rules

**T1 Pricing power.** `E = 2026-02-23`, `H = 8`, effect = mean gap over weeks
0–7. **PASS** unless the effect is below −10% **and** the placebo p-value is
below 0.10, which is **FAIL**. A *first stage* is also reported: protocol revenue
as a share of fees before and after `E`, to show the switch changed what NEAR
earns. User-facing fee rates around `E` are reported too: if users' price did
not change, T1 measures whether integrators and their flow left, not user price
sensitivity.

**T2 Trust shock.** `E = 2026-10-01`, `H = 6` (weeks 0–5, the most the
snapshot allows). The shock is the mean gap over weeks 0–1. The recovery
statistic is the mean gap over weeks 4–5, with its own placebo distribution.
**PASS** unless the recovery gap is below −10% **and** its placebo p-value is below
0.10, which is **FAIL**.

**T3 Price premium.** Over the last 26 complete event-weeks before `S`:

- Fee rate (bps) = weekly fees / weekly volume, per venue.
- Competitor rate = volume-weighted rate across THORChain, Chainflip and Maya
  for the venues observed that week.
- Premium weeks = share of weeks where Intents' rate is above the competitor rate.
- Share = Intents volume / (Intents + competitors' volume), log-share trend
  estimated by OLS; 90% CI by moving-block bootstrap (block 4, 2,000 draws,
  seed 7).

**PASS** if premium weeks ≥ 75% **and** the CI upper bound of the share slope is
≥ 0. **FAIL** otherwise. The elasticity of share to relative fee rate is reported
as descriptive only, because fee rates and route mix move together.

## 6. Overall verdict

Three passes: **strong moat evidence**. Two: **moderate**. One or none:
**weak**. The verdict is printed as computed, whichever way it falls.

## 7. Known limits, stated in advance

- DefiLlama is an aggregator. Its adapters can change history; the snapshot
  and hashes pin the version analysed.
- The donor pool is small, so placebo-in-space p-values have a floor around
  1/(donors+1).
- A synthetic control assumes no other Intents-specific shock in the window.
  Known overlapping events are listed in the report where found.
- Solver-level concentration is out of scope: in a 200-transaction sample of
  recent `intents.near` activity no `token_diff` swap events appeared, so solver
  identity can't be measured reliably from public data without the Explorer API.

## 8. Changes after pre-registration

None yet.
