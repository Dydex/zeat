"""On-chain sampling of NEAR Intents activity, straight from NEAR blocks.

Why: every other input is an aggregator (DefiLlama). This module reads the
chain itself, keylessly, from neardata.xyz (full blocks with receipts and
logs), to (1) check that DefiLlama's Intents series tracks real on-chain
activity, (2) give T2 an independent on-chain outcome, (3) time the Oct 1
pause on-chain, (4) measure solver concentration from `token_diff` events, and
(5) read NEAR's total supply from block headers.

Design:
- The *plan* (which block heights to read) is deterministic: week anchors found
  by search on block timestamps, then seeded uniform draws inside each week.
  It is saved to data/onchain/plan.json.
- The *sample* is one compact JSON line per block in data/onchain/blocks.jsonl,
  with the block hash, so anyone can re-fetch and compare
  (`python3 -m moat verify-onchain`). Blocks are immutable, so a re-fetch must
  match exactly.
- Fetching is resumable and polite (low concurrency, backoff on HTTP 429).
"""

import collections
import concurrent.futures as cf
import datetime as dt
import json
import random
import threading
import time
import urllib.error
import urllib.request

from .fetch import ROOT, USER_AGENT

BASE = "https://mainnet.neardata.xyz/v0/block/"
DIR = ROOT / "data" / "onchain"
PLAN = DIR / "plan.json"
BLOCKS = DIR / "blocks.jsonl"
CONTRACT = "intents.near"
UTC = dt.timezone.utc

# Sampling windows (inclusive start, exclusive end) and blocks per week.
WINDOWS = [
    # weekly index for T2 corroboration and aggregator validation
    dict(name="weekly", start="2026-04-02", end="2026-11-12", step_days=7, per_step=80),
    # around the fee switch
    dict(name="feeswitch", start="2025-12-29", end="2026-04-20", step_days=7, per_step=40),
    # dense, around the Oct 1 exploit, every 30 minutes
    dict(name="pause", start="2026-09-30", end="2026-10-03", step_days=None, every_minutes=30),
]
SEED = 20261112
SUPPLY_ANCHORS = ["2025-11-11", "2026-11-11"]


# ---------------------------------------------------------------- fetching

class Fetcher:
    def __init__(self, min_interval=0.4):
        self.lock = threading.Lock()
        self.next_ok = 0.0
        self.min_interval = min_interval
        self.stats = collections.Counter()

    def _wait(self):
        with self.lock:
            now = time.time()
            t = max(now, self.next_ok)
            self.next_ok = t + self.min_interval
        time.sleep(max(0.0, t - time.time()))

    def block(self, height, max_skip=20):
        """Return the first existing block at or after `height`."""
        for skip in range(max_skip):
            h = height + skip
            for attempt in range(10):
                self._wait()
                try:
                    req = urllib.request.Request(BASE + str(h), headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=90) as r:
                        body = r.read()
                    if body.strip() in (b"null", b""):
                        self.stats["missing"] += 1
                        break
                    self.stats["ok"] += 1
                    return json.loads(body)
                except urllib.error.HTTPError as e:
                    if e.code == 429:
                        self.stats["429"] += 1
                        with self.lock:
                            self.min_interval = min(self.min_interval * 1.3, 5.0)
                        time.sleep(min(60, 2 ** attempt))
                        continue
                    if e.code == 404:
                        self.stats["missing"] += 1
                        break
                    if e.code >= 500:
                        time.sleep(min(60, 2 ** attempt))
                        continue
                    raise
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    time.sleep(min(60, 2 ** attempt))
                    continue
            else:
                raise RuntimeError(f"giving up on block {h}")
        raise RuntimeError(f"no block found from {height} to {height + max_skip}")


def ts_of(block):
    return int(block["block"]["header"]["timestamp_nanosec"]) / 1e9


# ---------------------------------------------------------------- summary

def summarize(block):
    """Compact, deterministic summary of one block's intents.near activity."""
    hdr = block["block"]["header"]
    events = collections.Counter()
    preds = set()
    swap_accounts = []
    n_rx = n_fail = n_all = 0
    for shard in block.get("shards") or []:
        for r in shard.get("receipt_execution_outcomes") or []:
            n_all += 1
            if r["receipt"]["receiver_id"] != CONTRACT:
                continue
            out = r["execution_outcome"]["outcome"]
            if isinstance(out.get("status"), dict) and "Failure" in out["status"]:
                n_fail += 1
                continue
            n_rx += 1
            preds.add(r["receipt"]["predecessor_id"])
            for line in out.get("logs") or []:
                if not line.startswith("EVENT_JSON:"):
                    continue
                try:
                    ev = json.loads(line[11:])
                except ValueError:
                    events["_unparsed"] += 1
                    continue
                name = ev.get("event", "?")
                events[name] += 1
                if name == "token_diff":
                    for d in ev.get("data") or []:
                        if isinstance(d, dict) and "account_id" in d:
                            swap_accounts.append(d["account_id"])
    return dict(
        height=hdr["height"], hash=hdr["hash"], ts=int(hdr["timestamp_nanosec"]) // 10 ** 6,
        total_supply=hdr["total_supply"], receipts_all=n_all,
        intents_receipts=n_rx, intents_failed=n_fail, predecessors=len(preds),
        events=dict(sorted(events.items())), swap_accounts=sorted(swap_accounts),
    )


# ---------------------------------------------------------------- planning

class HeightFinder:
    """Find the first block at or after a timestamp.

    Every fetched block is kept as a reference point, so each new search starts
    from tight brackets and needs only a couple of fetches. Anchors are cached
    on disk, so an interrupted planning run resumes where it stopped.
    """

    def __init__(self, fetcher, tol_s=900):
        self.f, self.tol = fetcher, tol_s
        self.cache = DIR / "anchors_cache.json"
        self.known, self.found = {}, {}
        if self.cache.exists():
            c = json.loads(self.cache.read_text())
            self.known = {int(k): v for k, v in c["known"].items()}
            self.found = c["found"]

    def _save(self):
        DIR.mkdir(parents=True, exist_ok=True)
        self.cache.write_text(json.dumps(dict(known=self.known, found=self.found)))

    def _fetch(self, h):
        b = self.f.block(h)
        hh = b["block"]["header"]["height"]
        self.known[hh] = ts_of(b)
        return hh

    def find(self, key, target_ts, lo=150_000_000, hi=224_250_000):
        if key in self.found:
            return self.found[key]
        if not self.known:
            self._fetch(lo)
            self._fetch(hi)
        h = None
        for _ in range(40):
            pts = sorted(self.known.items())
            below = [q for q in pts if q[1] <= target_ts]
            above = [q for q in pts if q[1] > target_ts]
            if above and above[0][1] - target_ts <= self.tol:
                h = above[0][0]
                break
            if below and target_ts - below[-1][1] <= self.tol and not above:
                h = below[-1][0]
                break
            (h0, t0), (h1, t1) = below[-1], above[0]
            if h1 - h0 <= 2:
                h = h1
                break
            guess = int(h0 + (target_ts - t0) * (h1 - h0) / (t1 - t0))
            guess = min(max(guess, h0 + 1), h1 - 1)
            self._fetch(guess)
        self.found[key] = h
        self._save()
        return h


def day_ts(iso):
    return dt.datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp()


def make_plan(log=print):
    finder = HeightFinder(Fetcher(min_interval=0.3))
    anchors = {}

    def anchor(iso):
        if iso not in anchors:
            anchors[iso] = finder.find(iso, day_ts(iso))
            log(f"  anchor {iso} -> {anchors[iso]}  ({len(finder.known)} blocks looked up)")
        return anchors[iso]

    rng = random.Random(SEED)
    heights = []
    for w in WINDOWS:
        start, end = dt.date.fromisoformat(w["start"]), dt.date.fromisoformat(w["end"])
        if w.get("step_days"):
            d = start
            while d < end:
                e = min(d + dt.timedelta(w["step_days"]), end)
                h0, h1 = anchor(d.isoformat()), anchor(e.isoformat())
                for _ in range(w["per_step"]):
                    heights.append(dict(window=w["name"], height=rng.randrange(h0, h1)))
                d = e
        else:
            h0 = anchor(start.isoformat())
            h1 = anchor(end.isoformat())
            n = int((day_ts(w["end"]) - day_ts(w["start"])) / 60 / w["every_minutes"])
            for i in range(n):
                heights.append(dict(window=w["name"], height=h0 + round(i * (h1 - h0) / n)))
    for iso in SUPPLY_ANCHORS:
        heights.append(dict(window="supply", height=anchor(iso)))
    DIR.mkdir(parents=True, exist_ok=True)
    plan = dict(seed=SEED, windows=WINDOWS, anchors=anchors, source=BASE, blocks=heights)
    PLAN.write_text(json.dumps(plan, indent=1) + "\n")
    log(f"plan: {len(heights)} blocks -> {PLAN.relative_to(ROOT)}")
    return plan


# ---------------------------------------------------------------- sampling

def load_blocks():
    out = {}
    if BLOCKS.exists():
        for line in BLOCKS.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["requested"]] = row
    return out


def sample(workers=3, log=print):
    plan = json.loads(PLAN.read_text())
    done = load_blocks()
    todo = sorted({b["height"] for b in plan["blocks"]} - set(done))
    log(f"{len(done)} done, {len(todo)} to fetch")
    f = Fetcher(min_interval=0.5)
    lock = threading.Lock()
    t0 = time.time()

    def one(h):
        s = summarize(f.block(h))
        s["requested"] = h
        with lock:
            with BLOCKS.open("a") as fh:
                fh.write(json.dumps(s, sort_keys=True) + "\n")
        return h

    n = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for _ in cf.as_completed([ex.submit(one, h) for h in todo]):
            n += 1
            if n % 50 == 0:
                rate = n / (time.time() - t0)
                log(f"  {n}/{len(todo)}  {rate:.2f}/s  eta {(len(todo) - n) / rate / 60:.0f} min  {dict(f.stats)}")
    canonicalize()
    log("sampling complete")


def canonicalize():
    """Rewrite blocks.jsonl sorted and de-duplicated, so it diffs cleanly."""
    rows = load_blocks()
    BLOCKS.write_text("".join(json.dumps(rows[h], sort_keys=True) + "\n" for h in sorted(rows)))


def verify(n=20, seed=None, log=print):
    """Re-fetch n random sampled blocks and check their summaries match."""
    rows = load_blocks()
    rng = random.Random(seed)
    pick = rng.sample(sorted(rows), min(n, len(rows)))
    f = Fetcher()
    bad = 0
    for h in pick:
        s = summarize(f.block(h))
        s["requested"] = h
        if s != rows[h]:
            bad += 1
            log(f"  MISMATCH at {h}")
    log(f"verified {len(pick) - bad}/{len(pick)} sampled blocks against the chain")
    return bad == 0
