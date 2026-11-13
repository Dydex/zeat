"""Command line: python3 -m zeat [build|refresh|verify]."""

import sys
import time

USAGE = """usage: python3 -m zeat <command>

  build    verify the snapshot hashes, run the analysis, write
           results/results.json, site/index.html and THESIS.md (offline)
  refresh  download fresh data into data/raw and rewrite the manifest
  verify   check data/raw against data/manifest.json only

  onchain          plan (if needed) and fetch the on-chain block sample (slow, resumable)
  verify-onchain   re-fetch 20 random sampled blocks and check they match the chain
"""


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "build"
    if cmd == "refresh":
        from .fetch import refresh
        refresh()
    elif cmd == "verify":
        from .fetch import verify
        m = verify()
        print(f"ok: {len(m['files'])} files match the manifest (snapshot {m['snapshot_date']})")
    elif cmd == "onchain":
        from . import onchain
        if not onchain.PLAN.exists():
            onchain.make_plan()
        onchain.sample()
    elif cmd == "verify-onchain":
        from . import onchain
        return 0 if onchain.verify(n=int(argv[2]) if len(argv) > 2 else 20) else 1
    elif cmd == "build":
        from . import analysis, site, thesis
        t = time.time()
        print("verifying snapshot and running the three tests ...")
        res = analysis.run()
        paths = [analysis.write_results(res), site.render(res), thesis.render(res)]
        site.copy_docs()
        for name in ("t1", "t2", "t3"):
            r = res["tests"][name]
            print(f"  {name.upper()} {r['name']:15s} {r['verdict']}")
        print(f"verdict: {res['overall']} ({res['passes']}/3)")
        from .fetch import ROOT
        for p in paths:
            print(f"wrote {p.relative_to(ROOT)}")
        print(f"done in {time.time() - t:.0f}s")
    else:
        print(USAGE)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
