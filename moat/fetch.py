"""Download every source into data/raw/ and record a hashed manifest.

`python3 -m moat refresh` is the only network step. `build` works offline from
the committed snapshot, and refuses to run if a file no longer matches its hash.
"""

import datetime as dt
import hashlib
import json
import pathlib
import time
import urllib.request

from .sources import SOURCES

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifest.json"
USER_AGENT = "moat-test/1.0 (reproducible research script)"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get(url, attempts=4):
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:  # network hiccups: back off and retry
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"failed to fetch {url}: {last}")


def refresh(log=print):
    RAW.mkdir(parents=True, exist_ok=True)
    fetched_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    entries = []
    for s in SOURCES:
        body = _get(s["url"])
        json.loads(body)  # fail loudly on a non-JSON response
        path = RAW / f"{s['id']}.json"
        path.write_bytes(body)
        entries.append(dict(id=s["id"], url=s["url"], file=str(path.relative_to(ROOT)),
                            bytes=len(body), sha256=sha256(body)))
        log(f"  {s['id']:18s} {len(body):>9,d} bytes")
    manifest = dict(fetched_at=fetched_at.isoformat().replace("+00:00", "Z"),
                    snapshot_date=fetched_at.date().isoformat(), files=entries)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    log(f"snapshot {manifest['snapshot_date']} written to {MANIFEST.relative_to(ROOT)}")
    return manifest


def verify(manifest=None):
    """Raise if any raw file is missing or differs from the manifest hash."""
    manifest = manifest or json.loads(MANIFEST.read_text())
    bad = []
    for e in manifest["files"]:
        p = ROOT / e["file"]
        if not p.exists() or sha256(p.read_bytes()) != e["sha256"]:
            bad.append(e["file"])
    if bad:
        raise RuntimeError("snapshot files changed or missing: " + ", ".join(bad))
    return manifest
