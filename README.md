# potwatch

Health checks for Portaldot V3 networks, with tamper-evident health attestations on the Portaldot EVM.

Built for the Portaldot Hacker House 2026, Node Operations & Tooling track. All code in this repository was written during the event (October 14 to November 6, 2026).

## What it does

potwatch checks every layer of a Portaldot V3 network in one command. It reads the public Substrate RPC, the EVM RPC and the explorer API, decodes on-chain consensus state (BABE slots, GRANDPA rounds, session validators), and explains in plain language what is wrong and what to check next.

The results can be published on the Portaldot EVM through a small contract, `HealthAttestation`. Anyone can later check that a published report matches what was recorded on-chain.

potwatch is read-only. It needs no keys, and every RPC call goes through an allowlist of read-only methods in `potwatch/rpc.py`.

## Why it is needed

Portaldot V3 runs a Substrate chain (BABE for block production, GRANDPA for finality) with an EVM on top. When something breaks, what a dApp developer notices ("my transaction never confirms") is several layers away from the cause. The real problem might be a node with no peers, an offline GRANDPA voter, or an explorer that stopped indexing. potwatch looks at all of these at once and reports a short list of findings.

## What it found on its first run

The first real run was on October 28, 2026 at 23:56 UTC.

| Network | Verdict | Findings |
|---|---|---|
| PortaldotV3 Test (test-node-v3) | CRIT | The best block, #232115, was 11.2 hours old. The RPC node and the EVM RPC node had no peers. There were only 2 validators, so GRANDPA could not tolerate a single fault. |
| PortaldotV3 Live (live-v3-node) | WARN | 1 peer and only 2 validators. |
| Both networks | WARN | The same 2 validator accounts, BABE key and GRANDPA key were active on both networks. |

In the 120 blocks before the testnet stalled, blocks arrived every 6.0 seconds and both authorities produced blocks (58 and 62). Production stopped all at once rather than degrading slowly, which points to a network or host event rather than a slow validator.

The testnet resumed on October 29 at 02:09:54 UTC with block #232116, after a halt of 13 hours 24 minutes, on the same chain. At 08:32 UTC potwatch rated it WARN: blocks every 6.0 seconds, finality 2 blocks behind, still 1 peer and 2 validators.

The full output of the first run is in [`examples/2026-10-29/`](examples/2026-10-29/). It contains `report.json`, a self-contained `report.html` with block-time charts, and `metrics.prom` for Prometheus.

These are observations from public endpoints at one point in time, not a security audit. Reusing keys across networks may be intentional for a test deployment. potwatch flags it because an outage on one network can then affect the other.

## Project status

Done:

- The health checker (`potwatch check`, `potwatch watch` and `potwatch digest`), which runs against the live public endpoints.
- The rule engine, with offline tests on snapshots captured from the V3 networks.
- The `HealthAttestation` contract, with a build script and a test that runs without keys.
- A deployment dry-run against the public V3 testnet. The testnet node returns exactly the expected runtime code for the contract.
- A full deploy and first attestation on a local chain with the V3 chain id, reproducible with one script. See [Local deployment demo](#local-deployment-demo).
- A short terminal recording of the local deployment.

Not done yet:

- Deployment on the public V3 testnet. This needs testnet tokens (tPOT), which are only handed out through a manual faucet request in Portaldot's Discord. See [Testnet deployment](#testnet-deployment).
- A demo video of up to 3 minutes. The script is in [`docs/demo-script.md`](docs/demo-script.md).

Planned next:

- Scheduled attestations from a dedicated reporter key.
- Comparing an operator's own validator RPC with the public RPC (same height, same finalized block).
- Alerts by webhook or Discord when `potwatch watch` sees a state change.
- A small read-only web page that lists attestations from the contract and re-verifies them against the published reports.

## Architecture

```mermaid
flowchart TB
  subgraph NET["Portaldot V3 testnet (public endpoints)"]
    S["Substrate RPC<br/>BABE · GRANDPA · Session · Staking"]
    E["EVM RPC (pallet-revive eth-rpc)<br/>chain id 420420777"]
    X["Explorer API<br/>indexer status"]
    C[("HealthAttestation.sol<br/>on Portaldot EVM")]
  end
  subgraph PW["potwatch (read-only, no keys)"]
    RPC["rpc.py<br/>read-only method allowlist"]
    P["probe.py<br/>snapshot per layer"]
    H["history.py<br/>last N headers + BABE pre-digest"]
    R["rules.py<br/>findings, thresholds,<br/>cross-network checks"]
    O["render.py<br/>text · report.html · metrics.prom · report.json"]
    D["potwatch digest<br/>sha256 per network"]
    A["attest_calldata.py<br/>unsigned calldata"]
    V["deployment.py<br/>preflight dry-run · verify receipts"]
  end
  OP(["Operator wallet<br/>(MetaMask / cast) signs"])
  S --> RPC
  E --> RPC
  X --> P
  RPC --> P
  RPC --> H
  P --> R
  H --> R
  R --> O
  O --> D --> A --> OP
  OP -- "deploy + attest tx" --> C
  C -. "eth_getCode · latest(network)" .-> V
  E -. "eth_call dry-run · receipts" .-> V
  V --> Rd["README deployment block<br/>deployments/*.json"]
  Obs["Prometheus / cron / CI<br/>exit code 0·1·2"] --- O
```

The diagram is also available as [SVG](docs/architecture.svg) and [PNG](docs/architecture.png). [`docs/architecture.md`](docs/architecture.md) describes the data flow, the safety model and how many offline validators GRANDPA can tolerate.

## Checks

| Code | Severity | Meaning |
|---|---|---|
| `RPC_DOWN` | crit | The endpoint cannot be reached. |
| `WRONG_CHAIN` | crit | The endpoint serves a different chain than expected. |
| `HEAD_STALL` | crit | The best block is older than 10 times the observed block time. |
| `HEAD_SLOW` | warn | The best block is older than 3 times the observed block time. |
| `RPC_ISOLATED` | crit | The RPC node has no peers. |
| `LOW_PEERS` | warn | The RPC node has fewer than 2 peers. |
| `FINALITY_STALL` | crit | Finality is at least 50 blocks behind the best block. |
| `FINALITY_LAG` | warn | Finality is at least 10 blocks behind the best block. |
| `GRANDPA_MISSING_VOTES` | warn or crit | Finality is lagging and named voters are missing from the current round. |
| `GRANDPA_ROUND_OPEN` | info | A round is still collecting votes while finality keeps up. This is normal. |
| `SMALL_VALIDATOR_SET` | warn | Fewer than 4 validators. GRANDPA needs more than two thirds of the voters, so it tolerates `(n-1)//3` faults. |
| `SILENT_AUTHORITY` | warn | A BABE authority produced none of the last N blocks, based on the block header pre-digest. |
| `MISSED_SLOTS` | warn | Less than 90 % of BABE slots were filled. |
| `RPC_SLOW` | warn | RPC latency is above 1500 ms. |
| `EVM_RPC_DOWN` | crit | The EVM RPC cannot be reached. |
| `EVM_WRONG_CHAIN_ID` | crit | The EVM RPC reports an unexpected chain id. |
| `EVM_DIVERGENCE` | warn | The EVM head has drifted away from the Substrate head. |
| `EVM_RPC_ISOLATED` | warn | The EVM RPC node has no peers. |
| `EXPLORER_DOWN` | warn | The explorer API cannot be reached. |
| `INDEXER_LAG` | warn | The explorer is more than 20 blocks behind the finalized block. |
| `KEY_REUSE_ACROSS_NETWORKS` | warn | The same validator account, BABE key or GRANDPA key is active on more than one network. |
| `SESSION_KEY_EQUALS_ACCOUNT` | info | The BABE session key is the same as the validator account. |

The thresholds are defined in `potwatch/rules.py` (the `Thresholds` class). The rules are pure functions over a JSON snapshot, so they can be tested offline against real captured data.

## Install and run

You need Python 3.10 or newer and the `requests` package.

```bash
git clone https://github.com/sliarsgard/potwatch.git
cd potwatch
python3 -m pip install -r requirements.txt

# Check every network in networks.json once.
# Exit code: 0 = ok, 1 = warning, 2 = critical.
python3 -m potwatch check --history 120 --out out/

# Keep watching the testnet and log state changes to a file.
python3 -m potwatch watch --network portaldot-v3-testnet --interval 60 --log potwatch.jsonl

# Print the sha256 digest of each network in a report. This is what goes on-chain.
python3 -m potwatch digest --report out/report.json
```

With `--out DIR`, `check` writes three files:

- `report.json`, the full result.
- `report.html`, a report you can open directly in a browser.
- `metrics.prom`, for the Prometheus node_exporter textfile collector.

Because the exit code reflects the verdict, `check` works well from cron or a CI job.

To monitor another network, add an entry to `networks.json`:

```json
"my-node": {"substrate_rpc": "http://127.0.0.1:9944", "evm_rpc": "http://127.0.0.1:9933",
            "explorer_api": null, "expected_chain": "PortaldotV3 Test", "expected_evm_chain_id": 420420777}
```

## On-chain attestations

`contracts/HealthAttestation.sol` is an append-only log of report digests. A reporter records a report by calling:

```
attest(bytes32 digest, bytes32 network, uint64 bestBlock, uint64 finalized, uint64 takenAt, uint8 severity)
```

Anyone can then download the published `report.json`, run `potwatch digest` on it, and compare the result with `latest(network)` on-chain. Together these records form a public, timestamped uptime history for a network or a node operator that cannot be quietly changed afterwards.

The contract holds no funds. The owner can only add or remove reporters, and a report is rejected unless its `takenAt` is newer than the previous one.

To build and test the contract:

```bash
cd contracts
npm install
npm run build   # solc-js 0.8.24, EVM version paris; writes build/HealthAttestation.json
npm test        # 14 checks in an in-memory EVM, no keys needed
cd ..
```

To prepare an attestation, build unsigned calldata from a report and sign it with your own wallet:

```bash
python3 scripts/attest_calldata.py out/report.json --contract 0xYourDeployment
```

## Local deployment demo

The contract has been deployed and used end to end on a local chain rather than the public testnet, for two reasons:

- The V3 testnet halted on October 28 at block #232115 (last block at 12:45:54 UTC) and was down for 13 hours 24 minutes.
- Deploying there needs tPOT, and the only source we found is a manual faucet request in Portaldot's Discord. There is no public faucet page.

We also tried Portaldot's own local node, `portaldot_dev` v2.0.0 from [portaldotVolunteer/Portaldot-node](https://github.com/portaldotVolunteer/Portaldot-node). It has `pallet-contracts` but not `pallet-revive` or an Ethereum RPC, so it cannot run a Solidity contract. The demo therefore uses [anvil](https://book.getfoundry.sh/anvil/) configured with the V3 testnet's chain id, 420420777.

The demo deploys the exact committed contract build, attests a fresh potwatch report of the real public V3 testnet, and then reads everything back from the transaction receipts to verify it. Separately, the same bytecode was dry-run against the real V3 testnet, which returned exactly the expected runtime code.

Some limits apply. anvil is a standard EVM, not `pallet-revive`. Fees are not representative: about 0.001 ETH locally, against an estimated upper bound of about 209 tPOT on the testnet. There is also no explorer page for a local contract.

The demo only uses anvil's public, unlocked development account 0 (`0xf39F…2266`). Transactions are sent with `eth_sendTransaction`, so no private key is involved. `scripts/local_demo.sh` refuses to talk to any RPC other than `127.0.0.1` or `localhost`.

### Run it yourself (Linux or macOS)

You need Python 3.10 or newer, `jq` and Foundry (for `anvil` and `cast`).

```bash
# Install Foundry
curl -L https://foundry.paradigm.xyz | bash && ~/.foundry/bin/foundryup
export PATH="$HOME/.foundry/bin:$PATH"

# Get the code
git clone https://github.com/sliarsgard/potwatch.git
cd potwatch
python3 -m pip install -r requirements.txt

# Start a local chain with the V3 testnet chain id and leave it running
anvil --chain-id 420420777 --block-time 2 > anvil.log &

# Run the whole demo
./scripts/local_demo.sh
```

The script runs a preflight check, deploys the contract, runs a read-only potwatch check of the public testnet, attests the result and verifies it. These are the same steps done by hand:

```bash
RPC=http://127.0.0.1:8545
FROM=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266   # anvil development account 0 (unlocked)

python3 scripts/deployment.py --networks networks.local.json --network local-anvil preflight --from $FROM

DEPLOY_TX=$(cast send --rpc-url $RPC --unlocked --from $FROM --json \
  --create "$(jq -r .bytecode contracts/build/HealthAttestation.json)" | jq -r .transactionHash)
CONTRACT=$(cast receipt --rpc-url $RPC $DEPLOY_TX contractAddress)

# Exit code 1 means WARN, which is fine here
python3 -m potwatch check --network portaldot-v3-testnet --history 120 --out out/

CALLDATA=$(python3 scripts/attest_calldata.py out/report.json --contract $CONTRACT | jq -r '.[0].calldata')
ATTEST_TX=$(cast send --rpc-url $RPC --unlocked --from $FROM --json $CONTRACT $CALLDATA | jq -r .transactionHash)

python3 scripts/deployment.py --networks networks.local.json --network local-anvil verify \
  --deploy-tx $DEPLOY_TX --attest-tx $ATTEST_TX --write
```

On a fresh anvil chain the contract address is always `0x5FbDB2315678afecb367f032d93F642f64180aa3`, because it is the first transaction from account 0. The transaction hashes differ between runs because each attested report has a new timestamp.

### Recorded run (October 29, 2026)

The table below was filled in automatically by `deployment.py verify --write` from the local chain's receipts. The same data is saved in [`deployments/local-anvil.json`](deployments/local-anvil.json).

The attested report is in [`examples/2026-10-29-local-demo/`](examples/2026-10-29-local-demo/). Running `python3 -m potwatch digest --report examples/2026-10-29-local-demo/report.json` prints the same digest that `latest("portaldot-v3-testnet")` returned on-chain (`0x31eb…f773`).

<!-- deployment:start -->
| | |
|---|---|
| Network | Local anvil devnet, not the public V3 testnet (EVM chain id `420420777`) |
| Contract | `0x5fbdb2315678afecb367f032d93f642f64180aa3` |
| Deploy tx | `0xe46640073a7441b61e8b9a361120c854a29aebb768cf64e8b27be88527ecec77` (block #3) |
| First `attest` tx | `0xf63ea75caff7e2f854f712ef1ce787facb537e817f758752b2c59e8ee303af1a` (block #9) |
| Explorer | none (local chain, RPC `http://127.0.0.1:8545`) |
| Build | 0.8.24+commit.e11b9ed9.Emscripten.clang, evmVersion paris, optimizer 200 runs; on-chain code matches `contracts/build/HealthAttestation.json` byte-for-byte |
<!-- deployment:end -->

The run was recorded in the terminal. You can watch it as an [asciinema recording](demo/local-demo.cast) (`asciinema play demo/local-demo.cast`), a [GIF](demo/local-demo.gif) or an [MP4 video](demo/local-demo.mp4).

![Terminal recording of the local deployment](demo/local-demo.gif)

## Testnet deployment

On Portaldot V3, the EVM is provided by `pallet-revive` through an Ethereum JSON-RPC adapter (`web3_clientVersion` reports `eth-rpc`), so standard Ethereum tools work.

| | |
|---|---|
| EVM RPC | `https://test-evm-rpc-v3.portaldot.dev` |
| Chain id | 420420777 (`0x190f1ca9`) |
| Token | tPOT (14 decimals on Substrate, shown as 18 decimals over the Ethereum RPC) |
| Explorer | https://scanner-testnet-v3.portaldot.dev (a Substrate explorer, where EVM transactions appear as `revive` extrinsics) |
| Contract build | `contracts/build/HealthAttestation.json`, solc 0.8.24, EVM version paris, optimizer 200 runs, no constructor arguments |

After a testnet deployment, `scripts/deployment.py verify --write` replaces the table under [Recorded run](#recorded-run-october-29-2026) with the testnet results. That table should not be edited by hand.

### How to deploy with your own testnet account

potwatch never holds a key. Use a new account that only ever holds testnet tokens.

**1. Run the preflight check.** This is read-only. It checks the chain id and that the chain is producing blocks, dry-runs the contract constructor with `eth_call` to confirm the node returns the expected runtime code, and estimates the fee. With `--from` it also checks your balance.

```bash
python3 scripts/deployment.py preflight --from 0xYourTestnetAddress   # prints READY or NOT READY
```

On October 29 the dry-run returned the expected code. The fee estimate was at most about 209 tPOT, because `pallet-revive` includes the storage deposit in the gas figure. Fund the account with at least 250 tPOT.

**2. Deploy the contract build.** With Foundry, import the key into an encrypted keystore so it never appears in your shell history:

```bash
export RPC=https://test-evm-rpc-v3.portaldot.dev
cast wallet import potwatch-testnet --interactive
cast send --rpc-url $RPC --account potwatch-testnet --create "$(jq -r .bytecode contracts/build/HealthAttestation.json)"
# If the node rejects the transaction type, add --legacy
```

Note the `transactionHash` and `contractAddress` in the output.

If you prefer not to use a key in the terminal, you can use MetaMask and Remix instead. Add the network to MetaMask with the values above. In Remix, paste `contracts/HealthAttestation.sol`, compile it with solc 0.8.24, EVM version paris and the optimizer at 200 runs, and deploy with "Injected Provider". The `verify` step accepts code that differs only in the compiler's metadata hash.

**3. Publish the first attestation.**

```bash
python3 -m potwatch check --network portaldot-v3-testnet --history 120 --out examples/$(date +%F)/
python3 scripts/attest_calldata.py examples/$(date +%F)/report.json --contract 0xContract
cast send --rpc-url $RPC --account potwatch-testnet 0xContract <calldata printed by the previous command>
```

In Remix, use "At Address" to load the contract, then call `attest` with the values printed by `attest_calldata.py`. Severity is 0 for ok, 1 for info, 2 for warn and 3 for crit.

**4. Verify and record the deployment.**

```bash
python3 scripts/deployment.py verify --deploy-tx 0xDeployTx --attest-tx 0xAttestTx --write
```

This checks both receipts, confirms that the on-chain code matches the build, that `owner()` is the deployer and that `latest(network)` holds the attested digest. It then updates the deployment table in this README and writes `deployments/portaldot-v3-testnet.json`.

## Demo

- **Terminal demo of the local deployment:** [MP4](demo/local-demo.mp4), [GIF](demo/local-demo.gif) or [asciinema recording](demo/local-demo.cast). See [Local deployment demo](#local-deployment-demo).
- **Demo video (up to 3 minutes):** not recorded yet. The script is in [`docs/demo-script.md`](docs/demo-script.md).
- **Try it yourself:** no hosted service is needed. Follow [Install and run](#install-and-run), run `python3 -m potwatch check --out out/` against the public endpoints, and open `out/report.html`.
- **Pitch deck:** [`docs/pitch/potwatch-pitch.pdf`](docs/pitch/potwatch-pitch.pdf).

## Tests

```bash
python3 -m unittest discover -s tests -t .
cd contracts && npm install && npm test
```

The Python tests cover:

- SCALE compact decoding and SS58 address encoding, checked against the well-known Alice address.
- Decoding the BABE pre-digest from a real Portaldot block header.
- The rule engine, using snapshots captured from the public endpoints.
- Detection of keys reused across networks.
- Agreement between `potwatch digest` and the calldata builder.
- The deployment verifier, against a simulated chain (receipts, code match, owner and explorer links).

The contract test runs `HealthAttestation` in an in-memory EVM and covers access control, rejection of stale reports and `latest()`, in 14 checks.

The live endpoints are not covered by automated tests; running `check` exercises them. The deploy and attest transactions themselves are checked afterwards by `deployment.py verify`.

## Repository layout

| Path | Contents |
|---|---|
| `potwatch/rpc.py` | JSON-RPC client with a read-only method allowlist, batching and latency measurement |
| `potwatch/scale.py` | Minimal SCALE and SS58 decoding, without depending on substrate-interface |
| `potwatch/keys.py` | Storage keys for Timestamp, Session, Babe, Staking and Grandpa |
| `potwatch/babe.py` | Decoder for the BABE pre-runtime digest (authority index, slot and slot kind) |
| `potwatch/probe.py` | Snapshot of the Substrate RPC, EVM RPC and explorer API |
| `potwatch/history.py` | Statistics over the last N blocks: block time, slot fill, share per author and gaps |
| `potwatch/rules.py` | Findings, thresholds and cross-network checks, as pure functions |
| `potwatch/render.py` | Text, Prometheus and self-contained HTML output |
| `contracts/` | `HealthAttestation.sol`, its build script and the keyless EVM test |
| `scripts/` | `attest_calldata.py` (unsigned calldata), `deployment.py` (preflight and verify) and `local_demo.sh` (the local demo) |
| `networks.local.json` | The local anvil chain used by the deployment demo |
| `deployments/` | Receipts recorded by `deployment.py verify --write` |
| `demo/` | Terminal recording of the local deployment |
| `docs/` | Architecture notes, the demo video script and the pitch deck |

## Dependencies and disclosure

potwatch itself only depends on `requests`. Building and testing the contract uses solc-js, `@ethereumjs/evm`, `@ethereumjs/util` and `@ethereumjs/common`. The local deployment demo uses Foundry (`anvil` and `cast`) and `jq`, and the recording was made with asciinema and agg. Storage keys follow the standard Substrate scheme, `twox128(pallet) ++ twox128(item)`.

This project was built with substantial help from an AI coding assistant, under the submitter's direction and review.

## License

MIT
