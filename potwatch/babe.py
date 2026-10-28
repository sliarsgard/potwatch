"""Decode the BABE pre-runtime digest to find which authority produced a block."""
from __future__ import annotations

from .scale import compact, hex_bytes, u32, u64

PRE_RUNTIME = 6
BABE_ENGINE = b"BABE"
SLOT_KINDS = {1: "primary", 2: "secondary_plain", 3: "secondary_vrf"}


def babe_predigest(logs: list[str]) -> dict | None:
    """Return {'kind', 'authority_index', 'slot'} or None if the header has no BABE pre-digest."""
    for log in logs:
        b = hex_bytes(log)
        if len(b) < 6 or b[0] != PRE_RUNTIME or b[1:5] != BABE_ENGINE:
            continue
        _, n = compact(b, 5)
        data = b[5 + n:]
        kind = data[0]
        return {"kind": SLOT_KINDS.get(kind, f"unknown_{kind}"),
                "authority_index": u32(data, 1), "slot": u64(data, 5)}
    return None
