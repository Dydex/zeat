# Zeat: is NEAR Intents' revenue defensible?

**NEAR HACKATHON 2026 · Investment Thesis track**

Most NEAR theses measure how much NEAR Intents earns. This one asks the investor's next
question: **can it keep earning it?** A synthetic control built from competitors is the
counterfactual, so market-wide moves are never mistaken for NEAR-specific ones. Each claim
gets a placebo test.

**Demo video:** <https://x.com/dp7954/status/2121525982582702471> · **Live research note:** <https://dydex.github.io/zeat/> · **Thesis:** [THESIS.md](THESIS.md) · **Pre-registration:** [METHODS.md](METHODS.md)

> **For judges: a two-minute check.** Needs Python 3.10+ and nothing else (no installs, no keys).
>
> | Do | See |
> |---|---|
> | `python3 -m zeat verify` | `ok: 16 files match the manifest (snapshot 2026-11-12)` |
> | `python3 -m zeat build` (offline, ~40 s) | `T1 PASS`, `T2 FAIL`, `T3 FAIL`, `verdict: Weak moat evidence (1/3)` |
> | `git status --short` | no output: the build reproduced the committed results, dashboard and THESIS.md byte for byte |
> | `python3 -m unittest` | `OK` (25 tests: known-answer, injected-effect recovery, byte-exact rebuild) |
> | `python3 -m zeat verify-onchain 5` | `verified 5/5 sampled blocks against the chain` (needs internet) |
> | `git log --reverse --format='%h %ad %s' --date=iso` | METHODS.md (the pre-registration) was committed before any analysis code or result |
> | open `site/index.html` or <https://dydex.github.io/zeat/> | the research note: abstract and results table (Table 1), one numbered section per test with its figures and placebo tests, the on-chain check, the NEAR issuance comparison. Hover any chart for exact values |

| Test | Event | Question |
|---|---|---|
| **T1 Pricing power** | Fee switch, Feb 23, 2026 | When NEAR started taking a cut, did volume leave? |
| **T2 Trust shock** | $3.8M exploit, Oct 1, 2026 | Did volume come back after the exploit and pause? |
| **T3 Price premium** | Last 26 weeks | Does Intents charge more than rivals and still hold share? |

- **[THESIS.md](THESIS.md):** the claim, evidence for and against, and what would change my mind.
- **[METHODS.md](METHODS.md):** pre-registered rules and thresholds, committed before any result existed. Section 8 lists every later change, with reasons.
- **`site/index.html`:** the research note (the hosted page). Numbered sections and figures; every figure has a title, its takeaway and its source.
- **[results/results.json](results/results.json):** every number, machine-readable.
- **On-chain layer:** about 3,350 NEAR blocks are read directly, with no keys. They check the
  aggregator against the chain, look for the Oct 1 pause, measure solver concentration from
  `token_diff` swap events, and read NEAR's exact annual issuance from block headers.
- **Long-term NEAR case:** Intents revenue set against the value of NEAR issuance, and which
  revenue lever (cut, fee rate or volume) the moat tests say is safe to pull.

**Track hints used.** *Onchain data:* 3,346 NEAR blocks read directly, plus NEAR Intents
`token_diff` swap events. *Dashboards:* a static dashboard, rebuilt daily on fresh data by CI.
*Research:* a pre-registered causal design with placebo inference. *NEAR's role:* the subject is
NEAR Intents, the cross-chain settlement layer, and whether its fee revenue can offset NEAR's
issuance.

## Run it

```bash
python3 -m zeat build     # offline, ~40s: verifies data hashes, runs T1-T3 and the on-chain analyses,
                          # writes results/results.json, site/index.html, THESIS.md
python3 -m unittest       # the test suite, incl. known-answer checks and a byte-exact rebuild
python3 -m zeat refresh   # optional: fetch fresh public data, then build again
python3 -m zeat verify-onchain   # re-fetch 20 random sampled blocks, check they match the chain
python3 -m zeat onchain   # optional, slow: re-plan and re-fetch the whole block sample
```

The dashboard is published by CI to GitHub Pages. Pushes publish the pinned build. A daily job
publishes a **live** rebuild on fresh data under the same rules, and keeps the pinned build at `/pinned/`.
The hosted dashboard stays up through judging and at least until 2026-11-25.

Needs Python 3.10+ and nothing else: standard library only, no API keys, no installs.
`make`, `make test` and `make refresh` do the same.

## How it works

1. **Data:** 15 public DefiLlama series and NEAR's price from CoinGecko, covering NEAR Intents' volume, fees and revenue, plus
   competitors and the whole DEX market. They are snapshotted to `data/raw/` with a sha256 manifest.
   `build` refuses to run if any file changed.
2. **Controls:** native cross-chain venues (THORChain, Chainflip, Maya), aggregators with no
   known Intents route (SOCKET, 0x) and all-DEX volume. LI.FI, Rango and Bitget route part of
   their flow through Intents, so they are kept out of the control pool and used only as a
   sensitivity check.
3. **Estimator:** a synthetic control with intercept on log weekly volume. Time is counted in
   event-weeks from each event. Weights are fitted by accelerated projected gradient on the simplex.
4. **On-chain sample:** block heights come from a seeded plan (`data/onchain/plan.json`), and each
   block is reduced to a summary with its hash (`data/onchain/blocks.jsonl`).
5. **Inference:** placebo-in-time at every earlier date (primary) and placebo-in-space (secondary).
6. **Robustness:** leave-one-control-out, difference-in-differences, a 13-week pre-window, and
   adding the contaminated aggregators.

Every number in THESIS.md and on the dashboard is filled in by the build from
`results.json`; nothing is typed by hand.

## Layout

```
zeat/sources.py    every external input, with its role
zeat/fetch.py      download + sha256 manifest + verification
zeat/data.py       cleaning rules and event-week aggregation
zeat/stats.py      simplex projection, synthetic control, OLS, block bootstrap
zeat/analysis.py   T1, T2, T3, placebos, robustness, verdicts
zeat/onchain.py    block sampling plan, fetcher, block summaries, verification
zeat/chain.py      on-chain analyses and the NEAR issuance comparison
zeat/site.py       dashboard (inline SVG charts, light/dark)
zeat/thesis.py     THESIS.md
tests/             unit, known-answer and reproducibility tests
```

## Honesty notes

- The verdict is whatever the pre-registered rules return, including a negative one.
- One exploratory comparison was run before pre-registration. It is disclosed at the top of METHODS.md.
- The placebo test turned out to be biased by Intents' 2025 hypergrowth, not conservative as
  METHODS.md first claimed. This is disclosed, and a 2026-only diagnostic is reported alongside.

## Tools

Code and docs were written with AI coding assistance (Claude Code). Every number is computed
by the code from the pinned public data; nothing is typed by hand. All code was written during
the hackathon window (November 2026); no pre-existing libraries are used.

Not financial advice. MIT licence.
