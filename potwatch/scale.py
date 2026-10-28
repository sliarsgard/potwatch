"""Just enough SCALE decoding and SS58 encoding for the storage items potwatch reads."""
from __future__ import annotations

import hashlib

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def hex_bytes(h: str | None) -> bytes:
    if not h:
        return b""
    return bytes.fromhex(h[2:] if h.startswith("0x") else h)


def u32(b: bytes, o: int = 0) -> int:
    return int.from_bytes(b[o:o + 4], "little")


def u64(b: bytes, o: int = 0) -> int:
    return int.from_bytes(b[o:o + 8], "little")


def compact(b: bytes, o: int = 0) -> tuple[int, int]:
    """Decode a SCALE compact integer. Returns (value, bytes_consumed)."""
    mode = b[o] & 3
    if mode == 0:
        return b[o] >> 2, 1
    if mode == 1:
        return int.from_bytes(b[o:o + 2], "little") >> 2, 2
    if mode == 2:
        return int.from_bytes(b[o:o + 4], "little") >> 2, 4
    n = (b[o] >> 2) + 4
    return int.from_bytes(b[o + 1:o + 1 + n], "little"), 1 + n


def vec_account32(b: bytes) -> list[bytes]:
    n, off = compact(b)
    return [b[off + 32 * i: off + 32 * (i + 1)] for i in range(n)]


def vec_babe_authorities(b: bytes) -> list[tuple[bytes, int]]:
    """Vec<(sr25519 public key, u64 weight)>."""
    n, off = compact(b)
    out = []
    for i in range(n):
        base = off + 40 * i
        out.append((b[base:base + 32], u64(b, base + 32)))
    return out


def ss58(pub: bytes, prefix: int = 42) -> str:
    if prefix >= 64:
        raise ValueError("only simple prefixes supported")
    data = bytes([prefix]) + pub
    checksum = hashlib.blake2b(b"SS58PRE" + data, digest_size=64).digest()[:2]
    raw = data + checksum
    n = int.from_bytes(raw, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    pad = len(raw) - len(raw.lstrip(b"\0"))
    return "1" * pad + s
