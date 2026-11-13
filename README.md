# Moat Test: is NEAR Intents' revenue defensible?

**NEAR HACKATHON 2026 · Investment Thesis track**

Most NEAR theses measure how much NEAR Intents earns. This one asks the investor's next
question: **can it keep earning it?** A synthetic control built from competitors is the
counterfactual, so market-wide moves are never mistaken for NEAR-specific ones. Each claim
gets a placebo test.

**Live dashboard:** <https://dydex.github.io/near/> · **Thesis:** [THESIS.md](THESIS.md) · **Pre-registration:** [METHODS.md](METHODS.md)

> **For judges: a 60-second check.** Needs Python 3.10+ and nothing else.
> ```bash
> python3 -m moat verify && python3 -m moat build   # hashes match; every output rebuilt offline (~30s)
> git status --short                                # empty: the build reproduces the committed files
> python3 -m unittest                               # known-answer and byte-exact rebuild tests
> python3 -m moat verify-onchain 5                  # re-reads 5 sampled NEAR blocks; must match the chain
> git log --reverse --format='%h %ad %s' --date=iso # methods were committed before the results
> ```

| Test | Event | Question |
|---|---|---|
| **T1 Pricing power** | Fee switch, Feb 23, 2026 | When NEAR started taking a cut, did volume leave? |
| **T2 Trust shock** | $3.8M exploit, Oct 1, 2026 | Did volume come back after the exploit and pause? |
| **T3 Price premium** | Last 26 weeks | Does Intents charge more than rivals and still hold share? |

- **[THESIS.md](THESIS.md):** the claim, evidence for and against, and what would change my mind.
- **[METHODS.md](METHODS.md):** pre-registered rules and thresholds, committed before any result existed. Section 8 lists every later change, with reasons.
- **`site/index.html`:** the dashboard. Every chart has its source and one plain sentence.
- **[results/results.json](results/results.json):** every number, machine-readable.
- **On-chain layer:** about 3,350 NEAR blocks are read directly, with no keys. They check the
  aggregator against the chain, look for the Oct 1 pause, measure solver concentration from
  `token_diff` swap events, and read NEAR's exact annual issuance from block headers.
- **Long-term NEAR case:** Intents revenue set against the value of NEAR issuance, and which
  revenue lever (cut, fee rate or volume) the moat tests say is safe to pull.

## Run it

```bash
python3 -m moat build     # offline, ~30s: verifies data hashes, runs all tests,
                          # writes results/results.json, site/index.html, THESIS.md
python3 -m unittest       # the test suite, incl. known-answer checks and a byte-exact rebuild
python3 -m moat refresh   # optional: fetch fresh public data, then build again
python3 -m moat verify-onchain   # re-fetch 20 random sampled blocks, check they match the chain
python3 -m moat onchain   # optional, slow: re-plan and re-fetch the whole block sample
```

The dashboard is published by CI to GitHub Pages. Pushes publish the pinned build. A daily job
publishes a **live** rebuild on fresh data under the same rules, and keeps the pinned build at `/pinned/`.

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
moat/sources.py    every external input, with its role
moat/fetch.py      download + sha256 manifest + verification
moat/data.py       cleaning rules and event-week aggregation
moat/stats.py      simplex projection, synthetic control, OLS, block bootstrap
moat/analysis.py   T1, T2, T3, placebos, robustness, verdicts
moat/onchain.py    block sampling plan, fetcher, block summaries, verification
moat/chain.py      on-chain analyses and the NEAR issuance comparison
moat/site.py       dashboard (inline SVG charts, light/dark)
moat/thesis.py     THESIS.md
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
