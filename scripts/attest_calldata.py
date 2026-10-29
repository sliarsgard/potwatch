#!/usr/bin/env python3
"""Build UNSIGNED calldata for HealthAttestation.attest(...) from a potwatch report.json.

This script never touches keys and never sends anything. It prints, per network, the
calldata hex that a wallet (MetaMask, cast, etc.) can send to the deployed contract.

    python3 scripts/attest_calldata.py examples/2026-10-29/report.json [--contract 0x...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

SEVERITY = {"ok": 0, "info": 1, "warn": 2, "crit": 3}
ART = pathlib.Path(__file__).resolve().parent.parent / "contracts" / "build" / "HealthAttestation.json"


def network_digest(result: dict) -> str:
    """sha256 over the canonical JSON of one network's result (same encoding as `potwatch digest`)."""
    blob = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def b32(text: str) -> str:
    raw = text.encode()
    if len(raw) > 32:
        raise ValueError(f"network name longer than 32 bytes: {text}")
    return raw.hex().ljust(64, "0")


def word(n: int) -> str:
    return format(n, "064x")


def calldata(result: dict, selector: str) -> dict:
    snap = result["snapshot"]
    sub = snap["substrate"]
    d = network_digest(result)
    data = ("0x" + selector + d + b32(snap["network"]) + word(sub["best"]) + word(sub["finalized"])
            + word(snap["taken_at_ms"] // 1000) + word(SEVERITY[result["overall"]]))
    return {"network": snap["network"], "network_bytes32": "0x" + b32(snap["network"]), "digest": "0x" + d, "overall": result["overall"],
            "best": sub["best"], "finalized": sub["finalized"], "taken_at": snap["taken_at_ms"] // 1000,
            "calldata": data}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report")
    ap.add_argument("--contract", help="deployed HealthAttestation address (printed into the output only)")
    a = ap.parse_args(argv)
    art = json.loads(ART.read_text())
    selector = art["methodIdentifiers"]["attest(bytes32,bytes32,uint64,uint64,uint64,uint8)"]
    results = json.loads(pathlib.Path(a.report).read_text())
    out = [calldata(r, selector) for r in results]
    for o in out:
        o["to"] = a.contract or "<HealthAttestation address>"
        o["value"] = "0"
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
