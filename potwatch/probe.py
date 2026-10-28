"""One snapshot of a network: endpoints, heads, finality, peers, validator set, GRANDPA round."""
from __future__ import annotations

import time

import requests

from .keys import STORAGE
from .rpc import Rpc
from .scale import hex_bytes, u32, u64, vec_account32, vec_babe_authorities, ss58


def _storage(rpc: Rpc, pallet: str, item: str, at: str | None = None) -> bytes:
    params = [STORAGE[(pallet, item)]] + ([at] if at else [])
    res, _ = rpc.call("state_getStorage", params)
    return hex_bytes(res)


def probe_substrate(url: str, timeout: float = 10.0) -> dict:
    rpc = Rpc(url, timeout)
    out: dict = {"url": url, "ok": False}
    try:
        out["chain"], out["latency_ms"] = rpc.call("system_chain")
        out["version"], _ = rpc.call("system_version")
        out["health"], _ = rpc.call("system_health")
        out["sync"], _ = rpc.call("system_syncState")
        rv, _ = rpc.call("state_getRuntimeVersion")
        out["spec"] = {"name": rv.get("specName"), "version": rv.get("specVersion")}
        head, _ = rpc.call("chain_getHeader")
        fin_hash, _ = rpc.call("chain_getFinalizedHead")
        fin, _ = rpc.call("chain_getHeader", [fin_hash])
        out["best"] = int(head["number"], 16)
        out["finalized"] = int(fin["number"], 16)
        out["head_timestamp_ms"] = u64(_storage(rpc, "Timestamp", "Now"))
        validators = vec_account32(_storage(rpc, "Session", "Validators"))
        out["validators"] = [ss58(v) for v in validators]
        out["babe_authorities"] = [ss58(pk) for pk, _ in vec_babe_authorities(_storage(rpc, "Babe", "Authorities"))]
        ga, _ = rpc.call("state_call", ["GrandpaApi_grandpa_authorities", "0x"])
        out["grandpa_authorities"] = [ss58(pk) for pk, _ in vec_babe_authorities(hex_bytes(ga))]
        out["session_index"] = u32(_storage(rpc, "Session", "CurrentIndex"))
        out["grandpa_set_id"] = u64(_storage(rpc, "Grandpa", "CurrentSetId"))
        era = _storage(rpc, "Staking", "ActiveEra")
        if era:
            out["active_era"] = u32(era)
        vc = _storage(rpc, "Staking", "ValidatorCount")
        if vc:
            out["staking_validator_count_target"] = u32(vc)
        try:
            out["grandpa_round"], _ = rpc.call("grandpa_roundState")
        except Exception as e:  # some public nodes disable it
            out["grandpa_round_error"] = str(e)
        out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def probe_evm(url: str | None, timeout: float = 10.0) -> dict | None:
    if not url:
        return None
    rpc = Rpc(url, timeout)
    out: dict = {"url": url, "ok": False}
    try:
        cid, out["latency_ms"] = rpc.call("eth_chainId")
        out["chain_id"] = int(cid, 16)
        bn, _ = rpc.call("eth_blockNumber")
        out["block_number"] = int(bn, 16)
        gp, _ = rpc.call("eth_gasPrice")
        out["gas_price_wei"] = int(gp, 16)
        pc, _ = rpc.call("net_peerCount")
        out["peer_count"] = int(pc, 16)
        out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def probe_explorer(base: str | None, timeout: float = 10.0) -> dict | None:
    if not base:
        return None
    out: dict = {"url": base, "ok": False}
    try:
        t0 = time.perf_counter()
        r = requests.get(base.rstrip("/") + "/status", timeout=timeout)
        out["latency_ms"] = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        out["status"] = r.json()
        out["indexed_block"] = int(out["status"].get("block", 0))
        out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def snapshot(name: str, cfg: dict, timeout: float = 10.0) -> dict:
    return {
        "network": name,
        "taken_at_ms": int(time.time() * 1000),
        "expected_chain": cfg.get("expected_chain"),
        "expected_evm_chain_id": cfg.get("expected_evm_chain_id"),
        "substrate": probe_substrate(cfg["substrate_rpc"], timeout),
        "evm": probe_evm(cfg.get("evm_rpc"), timeout),
        "explorer": probe_explorer(cfg.get("explorer_api"), timeout),
    }
