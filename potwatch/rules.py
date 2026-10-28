"""Turn a snapshot (+ optional history summary) into findings. Pure functions, no I/O."""
from __future__ import annotations

from dataclasses import asdict, dataclass

OK, INFO, WARN, CRIT = "ok", "info", "warn", "crit"
ORDER = {OK: 0, INFO: 1, WARN: 2, CRIT: 3}


@dataclass
class Thresholds:
    expected_block_time_s: float = 6.0
    head_stall_factor: float = 10.0       # head older than 10 x block time -> crit
    head_slow_factor: float = 3.0         # older than 3 x -> warn
    finality_lag_warn: int = 10
    finality_lag_crit: int = 50
    evm_divergence_warn: int = 3
    indexer_lag_warn: int = 20
    latency_warn_ms: float = 1500.0
    min_validators_for_bft: int = 4


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    hint: str = ""


def grandpa_fault_tolerance(n: int) -> int:
    """How many GRANDPA voters can be offline while finality still progresses (needs > 2/3)."""
    return max(0, (n - 1) // 3)


def evaluate(snap: dict, hist: dict | None = None, th: Thresholds | None = None) -> list[Finding]:
    th = th or Thresholds()
    f: list[Finding] = []
    sub = snap["substrate"]
    if not sub.get("ok"):
        return [Finding("RPC_DOWN", CRIT, f"Substrate RPC {sub['url']} failed: {sub.get('error')}",
                        "Check the node process and the reverse proxy; try a second endpoint.")]
    exp = snap.get("expected_chain")
    if exp and sub.get("chain") != exp:
        f.append(Finding("WRONG_CHAIN", CRIT, f"Endpoint reports chain {sub.get('chain')!r}, expected {exp!r}."))
    block_time = th.expected_block_time_s
    if hist and hist.get("block_time_s", {}).get("median"):
        block_time = hist["block_time_s"]["median"]
    age_s = (snap["taken_at_ms"] - sub["head_timestamp_ms"]) / 1000
    if age_s > th.head_stall_factor * block_time:
        f.append(Finding("HEAD_STALL", CRIT,
                         f"Best block #{sub['best']} is {age_s/3600:.2f} h old (expected one block every ~{block_time:.0f} s).",
                         "Block production has stopped, or this node no longer receives blocks. Compare with a second node."))
    elif age_s > th.head_slow_factor * block_time:
        f.append(Finding("HEAD_SLOW", WARN, f"Best block is {age_s:.0f} s old."))
    peers = sub.get("health", {}).get("peers")
    if peers == 0 and sub.get("health", {}).get("shouldHavePeers"):
        f.append(Finding("RPC_ISOLATED", CRIT, "RPC node has 0 peers.",
                         "A public RPC node with no peers cannot see new blocks. Check bootnodes, firewall and the validators' p2p ports."))
    elif peers is not None and peers < 2:
        f.append(Finding("LOW_PEERS", WARN, f"RPC node has only {peers} peer(s)."))
    lag = sub["best"] - sub["finalized"]
    if lag >= th.finality_lag_crit:
        f.append(Finding("FINALITY_STALL", CRIT, f"Finality lags best by {lag} blocks."))
    elif lag >= th.finality_lag_warn:
        f.append(Finding("FINALITY_LAG", WARN, f"Finality lags best by {lag} blocks."))
    rnd = sub.get("grandpa_round")
    if rnd:
        best = rnd.get("best", {})
        missing_pv = best.get("prevotes", {}).get("missing", [])
        missing_pc = best.get("precommits", {}).get("missing", [])
        if missing_pc and lag < th.finality_lag_warn:
            f.append(Finding("GRANDPA_ROUND_OPEN", INFO,
                             f"GRANDPA round {best.get('round')} still collecting precommits; finality is keeping up (lag {lag})."))
        elif missing_pc:
            f.append(Finding("GRANDPA_MISSING_VOTES", CRIT if lag >= th.finality_lag_crit else WARN,
                             f"GRANDPA round {best.get('round')} (set {rnd.get('setId')}): "
                             f"{len(missing_pv)} voter(s) missing prevotes, {len(missing_pc)} missing precommits; "
                             f"weight {best.get('precommits', {}).get('currentWeight')}/{best.get('thresholdWeight')} needed.",
                             "Missing voters: " + ", ".join(sorted(set(missing_pv) | set(missing_pc)))))
    n = len(sub.get("validators", []))
    if n:
        tol = grandpa_fault_tolerance(n)
        if n < th.min_validators_for_bft:
            f.append(Finding("SMALL_VALIDATOR_SET", WARN,
                             f"{n} active validator(s): GRANDPA tolerates {tol} offline voter(s); any single outage halts finality.",
                             "Run at least 4 independent validators (tolerates 1 fault)."))
        else:
            f.append(Finding("VALIDATOR_SET", INFO, f"{n} active validators; GRANDPA tolerates {tol} offline."))
    if hist and hist.get("by_author") and n:
        produced = {a["authority_index"] for a in hist["by_author"]}
        silent = [i for i in range(len(sub.get("babe_authorities", []))) if i not in produced]
        if silent:
            names = [sub["babe_authorities"][i] for i in silent]
            f.append(Finding("SILENT_AUTHORITY", WARN,
                             f"{len(silent)} BABE authority(ies) authored 0 of the last {hist['blocks']} blocks: {', '.join(names)}"))
        if hist.get("slot_fill_rate") is not None and hist["slot_fill_rate"] < 0.9:
            f.append(Finding("MISSED_SLOTS", WARN,
                             f"Only {hist['slot_fill_rate']*100:.1f}% of slots filled over the last {hist['blocks']} blocks "
                             f"({hist['slots_missed']} missed)."))
    if sub.get("latency_ms", 0) > th.latency_warn_ms:
        f.append(Finding("RPC_SLOW", WARN, f"Substrate RPC latency {sub['latency_ms']:.0f} ms."))
    evm = snap.get("evm")
    if evm is not None:
        if not evm.get("ok"):
            f.append(Finding("EVM_RPC_DOWN", CRIT, f"EVM RPC failed: {evm.get('error')}"))
        else:
            want = snap.get("expected_evm_chain_id")
            if want and evm["chain_id"] != want:
                f.append(Finding("EVM_WRONG_CHAIN_ID", CRIT, f"eth_chainId {evm['chain_id']} != expected {want}."))
            d = abs(evm["block_number"] - sub["best"])
            if d > th.evm_divergence_warn:
                f.append(Finding("EVM_DIVERGENCE", WARN, f"EVM RPC is at #{evm['block_number']}, Substrate RPC at #{sub['best']} ({d} apart)."))
            if evm.get("peer_count") == 0:
                f.append(Finding("EVM_RPC_ISOLATED", WARN, "EVM RPC node reports 0 peers."))
    exp_api = snap.get("explorer")
    if exp_api is not None:
        if not exp_api.get("ok"):
            f.append(Finding("EXPLORER_DOWN", WARN, f"Explorer API failed: {exp_api.get('error')}"))
        elif sub["finalized"] - exp_api["indexed_block"] > th.indexer_lag_warn:
            f.append(Finding("INDEXER_LAG", WARN, f"Explorer indexed #{exp_api['indexed_block']}, finalized is #{sub['finalized']}."))
    if not any(ORDER[x.severity] >= ORDER[WARN] for x in f):
        f.append(Finding("HEALTHY", OK, "No problems detected."))
    return f


def compare_networks(snaps: list[dict]) -> list[tuple[str, Finding]]:
    """Cross-network checks. Returns (network, finding) pairs. Flags keys shared between networks."""
    out: list[tuple[str, Finding]] = []
    fields = [("validators", "session validator account"), ("babe_authorities", "BABE key"),
              ("grandpa_authorities", "GRANDPA key")]
    for i, a in enumerate(snaps):
        for b in snaps[i + 1:]:
            sa, sb = a["substrate"], b["substrate"]
            if not (sa.get("ok") and sb.get("ok")):
                continue
            for field, label in fields:
                shared = sorted(set(sa.get(field, [])) & set(sb.get(field, [])))
                if shared:
                    msg = (f"{len(shared)} {label}(s) are used on both {a['network']} and {b['network']}: "
                           + ", ".join(shared))
                    fd = Finding("KEY_REUSE_ACROSS_NETWORKS", WARN, msg,
                                 "Use separate keys and hosts per network so a test-network incident or "
                                 "key leak cannot affect the other network. Rotate session keys with author_rotateKeys on the node.")
                    out += [(a["network"], fd), (b["network"], fd)]
    for sa in snaps:
        s = sa["substrate"]
        if s.get("ok"):
            same = sorted(set(s.get("validators", [])) & set(s.get("babe_authorities", [])))
            if same:
                out.append((sa["network"], Finding("SESSION_KEY_EQUALS_ACCOUNT", INFO,
                            f"BABE session key equals the validator account for: {', '.join(same)}",
                            "Session keys are usually separate from the stash/controller account so they can be rotated.")))
    return out


def overall(findings: list[Finding]) -> str:
    return max((x.severity for x in findings), key=lambda s: ORDER[s], default=OK)


def as_dicts(findings: list[Finding]) -> list[dict]:
    return [asdict(x) for x in findings]
