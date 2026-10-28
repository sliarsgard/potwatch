"""Minimal JSON-RPC over HTTPS. Read-only: no signing, no key handling."""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

# Methods potwatch is allowed to call. Anything that writes or touches keys is absent on purpose.
READ_ONLY_METHODS = frozenset({
    "system_chain", "system_version", "system_health", "system_properties", "system_syncState",
    "system_nodeRoles", "chain_getHeader", "chain_getFinalizedHead", "chain_getBlockHash",
    "state_getStorage", "state_getRuntimeVersion", "state_call", "grandpa_roundState",
    "eth_chainId", "eth_blockNumber", "eth_gasPrice", "net_peerCount", "eth_getBlockByNumber",
})


READ_ONLY_RUNTIME_APIS = frozenset({"GrandpaApi_grandpa_authorities", "GrandpaApi_current_set_id"})


class RpcError(Exception):
    pass


@dataclass
class Rpc:
    url: str
    timeout: float = 10.0

    def __post_init__(self) -> None:
        self._session = requests.Session()
        self._id = 0

    def _check(self, method: str, params: list | None = None) -> None:
        if method not in READ_ONLY_METHODS:
            raise RpcError(f"method {method!r} is not on the read-only allowlist")
        if method == "state_call" and (not params or params[0] not in READ_ONLY_RUNTIME_APIS):
            raise RpcError("state_call is limited to read-only runtime APIs")

    def call(self, method: str, params: list | None = None) -> tuple[object, float]:
        """Return (result, latency_ms)."""
        self._check(method, params)
        self._id += 1
        t0 = time.perf_counter()
        r = self._session.post(self.url, json={"jsonrpc": "2.0", "id": self._id,
                                               "method": method, "params": params or []},
                               timeout=self.timeout)
        ms = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RpcError(f"{method}: {body['error']}")
        return body["result"], ms

    def batch(self, calls: list[tuple[str, list]]) -> list[object]:
        if not calls:
            return []
        for m, p in calls:
            self._check(m, p)
        payload = [{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)]
        r = self._session.post(self.url, json=payload, timeout=self.timeout * 3)
        r.raise_for_status()
        by_id = {x["id"]: x for x in r.json()}
        out = []
        for i in range(len(calls)):
            x = by_id.get(i, {})
            if "error" in x:
                raise RpcError(f"{calls[i][0]}: {x['error']}")
            out.append(x.get("result"))
        return out
