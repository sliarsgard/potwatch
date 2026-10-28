"""Walk back over recent blocks: block intervals, slot gaps and who authored what."""
from __future__ import annotations

import statistics
from collections import Counter

from .babe import babe_predigest
from .keys import STORAGE
from .rpc import Rpc
from .scale import hex_bytes, u64


def recent_blocks(url: str, count: int = 200, end: int | None = None, chunk: int = 50) -> list[dict]:
    rpc = Rpc(url, 15.0)
    if end is None:
        head, _ = rpc.call("chain_getHeader")
        end = int(head["number"], 16)
    start = max(1, end - count + 1)
    rows: list[dict] = []
    for lo in range(start, end + 1, chunk):
        nums = list(range(lo, min(end, lo + chunk - 1) + 1))
        hashes = rpc.batch([("chain_getBlockHash", [n]) for n in nums])
        headers = rpc.batch([("chain_getHeader", [h]) for h in hashes])
        stamps = rpc.batch([("state_getStorage", [STORAGE[("Timestamp", "Now")], h]) for h in hashes])
        for n, h, hd, ts in zip(nums, hashes, headers, stamps):
            pre = babe_predigest(hd["digest"]["logs"]) or {}
            rows.append({"number": n, "hash": h, "timestamp_ms": u64(hex_bytes(ts)),
                         "authority_index": pre.get("authority_index"), "slot": pre.get("slot"),
                         "slot_kind": pre.get("kind")})
    return rows


def summarize(rows: list[dict], authorities: list[str] | None = None) -> dict:
    if len(rows) < 2:
        return {"blocks": len(rows)}
    intervals = [(b["timestamp_ms"] - a["timestamp_ms"]) / 1000 for a, b in zip(rows, rows[1:])]
    slots = [r["slot"] for r in rows if r["slot"] is not None]
    slot_gaps = [b - a for a, b in zip(slots, slots[1:])]
    missed = sum(g - 1 for g in slot_gaps if g > 1)
    authors = Counter(r["authority_index"] for r in rows)
    kinds = Counter(r["slot_kind"] for r in rows)
    by_author = []
    for idx, n in sorted(authors.items(), key=lambda x: (x[0] is None, x[0])):
        label = authorities[idx] if authorities and idx is not None and idx < len(authorities) else str(idx)
        by_author.append({"authority_index": idx, "authority": label, "blocks": n,
                          "share": round(n / len(rows), 4)})
    q = statistics.quantiles(intervals, n=20) if len(intervals) >= 20 else None
    return {
        "blocks": len(rows),
        "from_block": rows[0]["number"], "to_block": rows[-1]["number"],
        "from_ms": rows[0]["timestamp_ms"], "to_ms": rows[-1]["timestamp_ms"],
        "block_time_s": {"mean": round(statistics.mean(intervals), 3),
                         "median": round(statistics.median(intervals), 3),
                         "p95": round(q[18], 3) if q else None,
                         "max": round(max(intervals), 3)},
        "slots_spanned": (slots[-1] - slots[0] + 1) if slots else None,
        "slots_missed": missed,
        "slot_fill_rate": round(len(slots) / (slots[-1] - slots[0] + 1), 4) if slots else None,
        "slot_kinds": dict(kinds),
        "by_author": by_author,
        "longest_gap": max(({"after_block": a["number"], "seconds": (b["timestamp_ms"] - a["timestamp_ms"]) / 1000}
                            for a, b in zip(rows, rows[1:])), key=lambda x: x["seconds"]),
    }
