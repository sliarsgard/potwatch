"""potwatch command line.

  python -m potwatch check  [--network NAME] [--history N] [--out DIR]
  python -m potwatch watch  [--network NAME] [--interval S] [--log FILE]
  python -m potwatch digest --report FILE      (hash for the on-chain attestation, no signing)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

from . import history as hist_mod
from . import render
from .probe import snapshot
from .rules import Finding, Thresholds, as_dicts, compare_networks, evaluate, overall

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXIT = {"ok": 0, "info": 0, "warn": 1, "crit": 2}


def load_networks(path: str | None) -> dict:
    p = pathlib.Path(path) if path else ROOT / "networks.json"
    return json.loads(p.read_text())


def run_check(name: str, cfg: dict, history_n: int, th: Thresholds, snap: dict | None = None) -> tuple[dict, list[float]]:
    snap = snap or snapshot(name, cfg)
    hist = None
    intervals: list[float] = []
    if history_n and snap["substrate"].get("ok"):
        rows = hist_mod.recent_blocks(cfg["substrate_rpc"], history_n, end=snap["substrate"]["best"])
        hist = hist_mod.summarize(rows, snap["substrate"].get("babe_authorities"))
        intervals = [(b["timestamp_ms"] - a["timestamp_ms"]) / 1000 for a, b in zip(rows, rows[1:])]
    findings = evaluate(snap, hist, th)
    return {"snapshot": snap, "history": hist, "findings": as_dicts(findings), "overall": overall(findings)}, intervals


def canonical_digest(report: dict) -> str:
    """sha256 over canonical JSON. Stable across key order."""
    blob = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    return "0x" + hashlib.sha256(blob).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="potwatch")
    ap.add_argument("--networks", help="path to networks.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--network", action="append", help="network name (repeatable); default all")
    c.add_argument("--history", type=int, default=120, help="blocks to sample (0 to skip)")
    c.add_argument("--out", help="directory for report.json, report.html, metrics.prom")
    w = sub.add_parser("watch")
    w.add_argument("--network", action="append")
    w.add_argument("--interval", type=float, default=60)
    w.add_argument("--log", default="potwatch.jsonl")
    w.add_argument("--iterations", type=int, default=0, help="0 = forever")
    d = sub.add_parser("digest")
    d.add_argument("--report", required=True)
    a = ap.parse_args(argv)

    nets = load_networks(a.networks)
    th = Thresholds()
    if a.cmd == "digest":
        rep = json.loads(pathlib.Path(a.report).read_text())
        print(canonical_digest(rep))
        return 0

    names = a.network or list(nets)
    if a.cmd == "check":
        results, ivs = [], {}
        snaps = {n: snapshot(n, nets[n]) for n in names}
        cross = compare_networks(list(snaps.values()))
        for n in names:
            r, iv = run_check(n, nets[n], a.history, th, snaps[n])
            extra = [fd for net, fd in cross if net == n]
            if extra:
                from dataclasses import asdict
                r["findings"] = [x for x in r["findings"] if x["code"] != "HEALTHY"] + [asdict(x) for x in extra]
                r["overall"] = overall([Finding(**x) for x in r["findings"]])
            results.append(r)
            ivs[n] = iv
            print(render.text(r))
        if a.out:
            out = pathlib.Path(a.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "report.json").write_text(json.dumps(results, indent=2))
            (out / "report.html").write_text(render.html_page(results, ivs))
            (out / "metrics.prom").write_text("".join(render.prometheus(r) for r in results))
            print(f"wrote {out}/report.json, report.html, metrics.prom")
        return max(EXIT[r["overall"]] for r in results)

    if a.cmd == "watch":
        last: dict[str, str] = {}
        i = 0
        while True:
            for n in names:
                r, _ = run_check(n, nets[n], 0, th)
                codes = ",".join(sorted(x["code"] for x in r["findings"]))
                if last.get(n) != codes:
                    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {n} -> {r['overall'].upper()} [{codes}]", flush=True)
                    last[n] = codes
                with open(a.log, "a") as fh:
                    fh.write(json.dumps({"network": n, "overall": r["overall"], "findings": r["findings"],
                                         "best": r["snapshot"]["substrate"].get("best"),
                                         "finalized": r["snapshot"]["substrate"].get("finalized"),
                                         "taken_at_ms": r["snapshot"]["taken_at_ms"]}) + "\n")
            i += 1
            if a.iterations and i >= a.iterations:
                return 0
            time.sleep(a.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
