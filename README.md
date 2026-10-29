# potwatch: health checks for Portaldot V3 networks

**Track:** Node Operations & Tooling (Portaldot Hacker House 2026)

potwatch is a read-only health checker for Portaldot V3. It connects to the public Substrate RPC, the EVM RPC and the explorer API, decodes on-chain state (BABE slots, GRANDPA rounds, session validators), and tells an operator in plain language what is wrong and what to check next. Its verdicts can be published on the Portaldot EVM as tamper-evident attestations through a small contract (`HealthAttestation`).

It needs no keys to run. All RPC calls go through an allowlist of read-only methods (`potwatch/rpc.py`).

## Why

Portaldot V3 runs a Substrate chain (BABE + GRANDPA) with an EVM on top. When something breaks, the symptom a dApp developer sees ("my tx never confirms") is several layers away from the cause (a node with 0 peers, a GRANDPA voter offline, an explorer that stopped indexing). potwatch checks every layer in one command and maps the result to a short list of findings.

### What it found on its first real run (2026-10-28, 23:56 UTC)

| Network | Verdict | Findings |
|---|---|---|
| `PortaldotV3 Test` (test-node-v3) | **CRIT** | best block #232115 is 11.2 h old (last block 12:45:54 UTC); RPC node and EVM RPC node have 0 peers; only 2 validators, so GRANDPA tolerates 0 faults |
| `PortaldotV3 Live` (live-v3-node) | **WARN** | 1 peer; only 2 validators |
| both | **WARN** | the same 2 session validator accounts, 1 BABE key and 1 GRANDPA key appear on both networks |

The full output is in [`examples/2026-10-29/`](examples/2026-10-29/): `report.json`, a self-contained `report.html` with block-time charts, and `metrics.prom` for Prometheus. In the 120 blocks before the testnet stalled, block time was a steady 6.0 s and both authorities authored blocks (58 / 62). In other words, production stopped all at once, with no gradual degradation beforehand. That points to a network or host event rather than a slow validator.

> These are observations from public endpoints at one point in time, not a security audit. Key reuse across networks may be intentional for a test deployment. potwatch flags it because it couples the failure domains of the two networks.

## Checks

| Code | Severity | What it means |
|---|---|---|
| `RPC_DOWN` / `WRONG_CHAIN` | crit | endpoint unreachable, or serving a different chain than expected |
| `HEAD_STALL` / `HEAD_SLOW` | crit / warn | best block older than 10x / 3x the observed block time |
| `RPC_ISOLATED` / `LOW_PEERS` | crit / warn | RPC node has 0 / fewer than 2 peers |
| `FINALITY_STALL` / `FINALITY_LAG` | crit / warn | best minus finalized is at least 50 / at least 10 blocks |
| `GRANDPA_MISSING_VOTES` | warn / crit | finality is lagging and named voters are missing from the current round |
| `GRANDPA_ROUND_OPEN` | info | round still collecting votes while finality keeps up (normal) |
| `SMALL_VALIDATOR_SET` | warn | fewer than 4 validators; GRANDPA needs more than 2/3 of voters, so it tolerates `(n-1)//3` faults |
| `SILENT_AUTHORITY` | warn | a BABE authority authored 0 of the last N blocks (decoded from the header pre-digest) |
| `MISSED_SLOTS` | warn | less than 90 % of BABE slots filled |
| `RPC_SLOW` | warn | RPC latency above 1500 ms |
| `EVM_RPC_DOWN` / `EVM_WRONG_CHAIN_ID` / `EVM_DIVERGENCE` / `EVM_RPC_ISOLATED` | crit / crit / warn / warn | EVM layer problems, including the EVM head drifting from the Substrate head |
| `EXPLORER_DOWN` / `INDEXER_LAG` | warn | explorer API down, or more than 20 blocks behind finalized |
| `KEY_REUSE_ACROSS_NETWORKS` | warn | the same validator account, BABE key or GRANDPA key is active on more than one network |
| `SESSION_KEY_EQUALS_ACCOUNT` | info | BABE session key equals the validator account |

The thresholds live in `potwatch/rules.py` (`Thresholds`). The rules are pure functions over a JSON snapshot, so they are tested offline against real captured snapshots.

## Install and run

Requires Python 3.10+ and `requests`.

```bash
git clone <this repo> && cd potwatch
python3 -m pip install -r requirements.txt

# one-shot check of every network in networks.json; exit code 0 ok, 1 warn, 2 crit
python3 -m potwatch check --history 120 --out out/

# only the testnet, and keep watching; log state changes to a JSONL file
python3 -m potwatch watch --network portaldot-v3-testnet --interval 60 --log potwatch.jsonl

# per-network sha256 digests of a report (what goes on-chain)
python3 -m potwatch digest --report out/report.json
```

`check --out DIR` writes `report.json`, `report.html` (open it in a browser, no server needed) and `metrics.prom` (point a node_exporter textfile collector at it). The exit code makes it usable from cron or CI.

To add a network, add an entry to `networks.json`:

```json
"my-node": {"substrate_rpc": "http://127.0.0.1:9944", "evm_rpc": "http://127.0.0.1:9933",
            "explorer_api": null, "expected_chain": "PortaldotV3 Test", "expected_evm_chain_id": 420420777}
```

## On-chain attestations (Portaldot EVM)

`contracts/HealthAttestation.sol` is an append-only log of report digests. A reporter calls

```
attest(bytes32 digest, bytes32 network, uint64 bestBlock, uint64 finalized, uint64 takenAt, uint8 severity)
```

Anyone can then fetch the published `report.json`, run `potwatch digest`, and compare the result with `latest(network)` on-chain. This gives a public, timestamped and tamper-evident uptime record for a network or a node operator. The contract holds no funds. The owner can only add or remove reporters, and stale reports (where `takenAt` is not newer than the last one) are rejected.

```bash
cd contracts && npm install
npm run build   # solc-js 0.8.24, evmVersion paris (no PUSH0) -> build/HealthAttestation.json
npm test        # keyless test in an in-memory EVM (14 checks)
cd ..
# build UNSIGNED calldata for attest() from a report; sign and send it with your own wallet
python3 scripts/attest_calldata.py out/report.json --contract 0xYourDeployment
```

Portaldot V3 testnet EVM: RPC `https://test-evm-rpc-v3.portaldot.dev`, chain id `420420777` (`0x190f1ca9`), token tPOT.

**Testnet deployment:** _to be filled in after deployment: contract address, deploy tx hash, first `attest` tx hash._

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

The tests cover SCALE compact decoding, SS58 encoding (checked against the well-known Alice address), BABE pre-digest decoding of a real Portaldot header log, the rule engine on snapshots captured from the public endpoints, cross-network key-reuse detection, and agreement between `potwatch digest` and the calldata builder.

## Layout

```
potwatch/rpc.py      JSON-RPC client with a read-only method allowlist, batching, latency
potwatch/scale.py    minimal SCALE + SS58 decoding (no substrate-interface dependency)
potwatch/keys.py     twox128 storage keys for Timestamp, Session, Babe, Staking, Grandpa
potwatch/babe.py     BABE pre-runtime digest decoder (authority index, slot, slot kind)
potwatch/probe.py    snapshot of Substrate RPC, EVM RPC and explorer API
potwatch/history.py  last-N-block statistics: block time, slot fill, per-author share, gaps
potwatch/rules.py    findings, thresholds and cross-network checks (pure functions)
potwatch/render.py   text, Prometheus and self-contained HTML output
contracts/           HealthAttestation.sol, build script, keyless EVM test
scripts/             attest_calldata.py (unsigned calldata)
docs/architecture.md
```

## Disclosure

- Dependencies: `requests` (Python). For contract build and test only: `solc` (solc-js), `@ethereumjs/evm`, `@ethereumjs/util`, `@ethereumjs/common`. Storage key prefixes follow the standard Substrate `twox128(pallet) ++ twox128(item)` scheme.
- This project was built with substantial help from an AI coding assistant, under the submitter's direction and review.

## License

MIT
