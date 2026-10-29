#!/usr/bin/env python3
"""Read-only helpers around deploying HealthAttestation to the Portaldot V3 testnet.

This script never signs or sends anything. `preflight` checks the network and dry-runs
the deployment with eth_call; `verify` reads back a deployment someone else sent and
records the contract address, tx hashes and explorer links.

    python3 scripts/deployment.py preflight [--from 0xYourAddress]
    python3 scripts/deployment.py verify --deploy-tx 0x... [--attest-tx 0x...] [--write]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from potwatch.rpc import Rpc  # noqa: E402

ART = ROOT / "contracts" / "build" / "HealthAttestation.json"
OUT = ROOT / "deployments"
START, END = "<!-- deployment:start -->", "<!-- deployment:end -->"


def load(network: str) -> tuple[dict, dict]:
    nets = json.loads((ROOT / "networks.json").read_text())
    return nets[network], json.loads(ART.read_text())


def selector(art: dict, sig: str) -> str:
    return "0x" + art["methodIdentifiers"][sig]


def strip_metadata(code: str) -> str:
    """Drop solc's trailing CBOR metadata, which differs between e.g. Remix and build.js for identical source."""
    code = code.lower().removeprefix("0x")
    if len(code) < 4:
        return code
    n = int(code[-4:], 16)
    return code[: -(n + 2) * 2] if (n + 2) * 2 <= len(code) else code


def code_match(onchain: str, built: str) -> str:
    if onchain.lower() == built.lower():
        return "exact"
    if strip_metadata(onchain) == strip_metadata(built):
        return "same-except-metadata"
    return "different"


def eth_call(rpc: Rpc, to: str | None, data: str) -> str:
    tx = {"data": data} if to is None else {"to": to, "data": data}
    return rpc.call("eth_call", [tx, "latest"])[0]


def preflight(cfg: dict, art: dict, sender: str | None) -> int:
    rpc = Rpc(cfg["evm_rpc"], timeout=20)
    chain_id = int(rpc.call("eth_chainId")[0], 16)
    block = int(rpc.call("eth_blockNumber")[0], 16)
    head = rpc.call("eth_getBlockByNumber", ["latest", False])[0]
    age = time.time() - int(head["timestamp"], 16)
    gas_price = int(rpc.call("eth_gasPrice")[0], 16)
    runtime = eth_call(rpc, None, art["bytecode"])
    gas = int(rpc.call("eth_estimateGas", [{"data": art["bytecode"]}])[0], 16)
    report = {
        "evm_rpc": cfg["evm_rpc"], "chain_id": chain_id, "chain_id_ok": chain_id == cfg["expected_evm_chain_id"],
        "evm_block": block, "head_age_s": round(age, 1), "gas_price_wei": gas_price,
        "deploy_dry_run_returns_expected_code": runtime.lower() == art["deployedBytecode"].lower(),
        "deploy_estimate_gas": gas, "deploy_max_fee_tpot": round(gas * gas_price / 1e18, 4),
    }
    if sender:
        report["from"] = sender
        report["balance_tpot"] = int(rpc.call("eth_getBalance", [sender, "latest"])[0], 16) / 1e18
        report["nonce"] = int(rpc.call("eth_getTransactionCount", [sender, "latest"])[0], 16)
    json.dump(report, sys.stdout, indent=1)
    print()
    ok = report["chain_id_ok"] and report["deploy_dry_run_returns_expected_code"] and age < 120
    if sender:
        ok = ok and report["balance_tpot"] * 1e18 >= gas * gas_price
    print("READY" if ok else "NOT READY", file=sys.stderr)
    return 0 if ok else 1


def revive_extrinsic(items: list[dict], tx_index: int) -> dict | None:
    """Pick the explorer extrinsic carrying an EVM tx: the only revive call in the block, else the one at tx_index."""
    revive = [x for x in items if x.get("call", {}).get("section") == "revive"]
    if len(revive) == 1:
        return revive[0]
    for x in revive:
        if x["indexer"]["extrinsicIndex"] == tx_index:
            return x
    return None


def explorer_links(cfg: dict, receipt: dict) -> dict:
    height = int(receipt["blockNumber"], 16)
    links = {"block": f"{cfg['explorer_ui']}/blocks/{height}"}
    try:
        r = requests.get(f"{cfg['explorer_api']}/blocks/{height}/extrinsics", params={"page_size": 100}, timeout=20)
        r.raise_for_status()
        x = revive_extrinsic(r.json().get("items", []), int(receipt["transactionIndex"], 16))
    except (requests.RequestException, ValueError):
        x = None
    if x:
        links["extrinsic"] = f"{cfg['explorer_ui']}/extrinsics/{height}-{x['indexer']['extrinsicIndex']}"
    return links


def receipt_of(rpc: Rpc, tx: str) -> dict:
    r = rpc.call("eth_getTransactionReceipt", [tx])[0]
    if not r:
        raise SystemExit(f"no receipt for {tx} yet (not mined, or wrong network)")
    if int(r["status"], 16) != 1:
        raise SystemExit(f"{tx} reverted (status {r['status']})")
    return r


def verify(network: str, cfg: dict, art: dict, deploy_tx: str, attest_tx: str | None) -> dict:
    rpc = Rpc(cfg["evm_rpc"], timeout=20)
    rec = receipt_of(rpc, deploy_tx)
    addr = rec.get("contractAddress")
    if not addr:
        raise SystemExit(f"{deploy_tx} is not a contract creation")
    code = rpc.call("eth_getCode", [addr, "latest"])[0]
    owner = "0x" + eth_call(rpc, addr, selector(art, "owner()"))[-40:]
    out = {
        "network": network, "chain_id": cfg["expected_evm_chain_id"], "contract": addr,
        "code_match": code_match(code, art["deployedBytecode"]),
        "owner": owner, "owner_is_deployer": owner.lower() == rec["from"].lower(),
        "compiler": art["compiler"], "evm_version": art["evmVersion"],
        "deploy": {"tx": deploy_tx, "block": int(rec["blockNumber"], 16), "links": explorer_links(cfg, rec)},
        "count": int(eth_call(rpc, addr, selector(art, "count()")), 16),
    }
    if attest_tx:
        a = receipt_of(rpc, attest_tx)
        logs = [lg for lg in a["logs"] if lg["address"].lower() == addr.lower() and len(lg["topics"]) == 3]
        if (a.get("to") or "").lower() != addr.lower() or not logs:
            raise SystemExit(f"{attest_tx} did not emit Attested on {addr}")
        net_b32 = logs[0]["topics"][2]
        latest = eth_call(rpc, addr, selector(art, "latest(bytes32)") + net_b32[2:])
        out["attest"] = {"tx": attest_tx, "block": int(a["blockNumber"], 16), "links": explorer_links(cfg, a),
                         "network": bytes.fromhex(net_b32[2:]).rstrip(b"\0").decode(errors="replace"),
                         "latest_digest": "0x" + latest[2:66]}
    if out["code_match"] == "different" or not out["owner_is_deployer"]:
        raise SystemExit("deployed code or owner does not match the build: " + json.dumps(out, indent=1))
    return out


def markdown(d: dict) -> str:
    dep = d["deploy"]
    rows = [
        "| | |", "|---|---|",
        f"| Network | Portaldot V3 testnet (EVM chain id `{d['chain_id']}`) |",
        f"| Contract | `{d['contract']}` |",
        f"| Deploy tx | `{dep['tx']}` (block #{dep['block']}) |",
    ]
    if "attest" in d:
        rows.append(f"| First `attest` tx | `{d['attest']['tx']}` (block #{d['attest']['block']}) |")
    links = [f"[deploy block]({dep['links']['block']})"]
    if "extrinsic" in dep["links"]:
        links.append(f"[deploy extrinsic]({dep['links']['extrinsic']})")
    if "attest" in d:
        al = d["attest"]["links"]
        links.append(f"[attest extrinsic]({al['extrinsic']})" if "extrinsic" in al else f"[attest block]({al['block']})")
    rows.append(f"| Explorer | {' · '.join(links)} |")
    match = {"exact": "byte-for-byte", "same-except-metadata": "except the solc metadata hash"}[d["code_match"]]
    rows.append(f"| Build | {d['compiler']}, evmVersion {d['evm_version']}, optimizer 200 runs; on-chain code matches "
                f"`contracts/build/HealthAttestation.json` {match} |")
    return "\n".join(rows)


def replace_block(text: str, body: str) -> str:
    pat = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pat.search(text):
        raise ValueError("deployment markers not found")
    return pat.sub(lambda _: f"{START}\n{body}\n{END}", text, count=1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--network", default="portaldot-v3-testnet")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preflight")
    p.add_argument("--from", dest="sender")
    v = sub.add_parser("verify")
    v.add_argument("--deploy-tx", required=True)
    v.add_argument("--attest-tx")
    v.add_argument("--write", nargs="*", metavar="FILE",
                   help="replace the deployment block in README.md (and any extra FILEs) and save deployments/<network>.json")
    a = ap.parse_args(argv)
    cfg, art = load(a.network)
    if a.cmd == "preflight":
        return preflight(cfg, art, a.sender)
    d = verify(a.network, cfg, art, a.deploy_tx, a.attest_tx)
    md = markdown(d)
    print(json.dumps(d, indent=1))
    print(md)
    if a.write is not None:
        OUT.mkdir(exist_ok=True)
        (OUT / f"{a.network}.json").write_text(json.dumps(d, indent=1) + "\n")
        for f in [ROOT / "README.md", *map(pathlib.Path, a.write)]:
            f.write_text(replace_block(f.read_text(), md))
            print("updated", f, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
