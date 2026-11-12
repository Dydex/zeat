# Moat Test: is NEAR Intents' revenue defensible?

**NEAR HACKATHON 2026 · Investment Thesis track**

Most NEAR theses measure how much NEAR Intents earns. This one asks the investor's next
question: **can it keep earning it?** A synthetic control built from competitors is the
counterfactual, so market-wide moves are never mistaken for NEAR-specific ones. Each claim
gets a placebo test.

| Test | Event | Question |
|---|---|---|
| **T1 Pricing power** | Fee switch, Feb 23, 2026 | When NEAR started taking a cut, did volume leave? |
| **T2 Trust shock** | $3.8M exploit, Oct 1, 2026 | Did volume come back after the exploit and pause? |
| **T3 Price premium** | Last 26 weeks | Does Intents charge more than rivals and still hold share? |

- **[THESIS.md](THESIS.md):** the claim, evidence for and against, and what would change my mind.
- **[METHODS.md](METHODS.md):** pre-registered rules and thresholds, committed before any result existed. Section 8 lists every later change, with reasons.
- **`site/index.html`:** the dashboard. Every chart has its source and one plain sentence.
- **[results/results.json](results/results.json):** every number, machine-readable.

## Run it

```bash
python3 -m moat build     # offline, ~30s: verifies data hashes, runs all tests,
                          # writes results/results.json, site/index.html, THESIS.md
python3 -m unittest       # 19 tests, incl. known-answer checks and a byte-exact rebuild
python3 -m moat refresh   # optional: fetch fresh public data, then build again
```

Needs Python 3.10+ and nothing else: standard library only, no API keys, no installs.
`make`, `make test` and `make refresh` do the same.

## How it works

1. **Data:** 15 public DefiLlama series, covering NEAR Intents' volume, fees and revenue, plus
   competitors and the whole DEX market. They are snapshotted to `data/raw/` with a sha256 manifest.
   `build` refuses to run if any file changed.
2. **Controls:** native cross-chain venues (THORChain, Chainflip, Maya), aggregators with no
   known Intents route (SOCKET, 0x) and all-DEX volume. LI.FI, Rango and Bitget route part of
   their flow through Intents, so they are kept out of the control pool and used only as a
   sensitivity check.
3. **Estimator:** a synthetic control with intercept on log weekly volume. Time is counted in
   event-weeks from each event. Weights are fitted by accelerated projected gradient on the simplex.
4. **Inference:** placebo-in-time at every earlier date (primary) and placebo-in-space (secondary).
5. **Robustness:** leave-one-control-out, difference-in-differences, a 13-week pre-window, and
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
moat/site.py       dashboard (inline SVG charts, light/dark)
moat/thesis.py     THESIS.md
tests/             unit, known-answer and reproducibility tests
```

## Honesty notes

- The verdict is whatever the pre-registered rules return, including a negative one.
- One exploratory comparison was run before pre-registration. It is disclosed at the top of METHODS.md.
- The placebo test turned out to be biased by Intents' 2025 hypergrowth, not conservative as
  METHODS.md first claimed. This is disclosed, and a 2026-only diagnostic is reported alongside.

Not financial advice. MIT licence.
