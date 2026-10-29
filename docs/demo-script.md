# Demo video script

The video should run about 2 minutes 55 seconds and must not exceed 3 minutes. It is a screen recording of a terminal and a browser, with a voice-over or captions. The times below are targets.

## 1. Introduction (0:00 to 0:15)

Show the title slide and say: "potwatch tells you when a Portaldot network is unhealthy and why, and lets you prove it on-chain."

## 2. One command (0:15 to 0:50)

Optionally mention that on October 28 potwatch caught the V3 testnet halting for 13 hours.

Run `python3 -m potwatch check --history 120 --out out/`. Scroll through the output for both networks and point out the CRIT and WARN lines and their hints. Then run `echo $?` to show that the exit code is 2 when there is a critical finding, which is what cron and CI jobs use.

## 3. The report (0:50 to 1:20)

Open `out/report.html` in a browser. Show the block-time chart, how blocks are split between authors, and the finding about keys reused across networks.

## 4. Monitoring (1:20 to 1:35)

Run `head out/metrics.prom` to show the Prometheus metrics, then `python3 -m potwatch watch --iterations 2 --interval 10` to show watch mode.

## 5. On-chain attestation (1:35 to 2:30)

1. Run `python3 -m potwatch digest --report out/report.json` to show the report digest.
2. Run `python3 scripts/attest_calldata.py out/report.json --contract <address>` to build the transaction data.
3. Show the deployed `HealthAttestation` contract and the `attest` transaction, with the same digest in the `Attested` event. For the local deployment, `./scripts/local_demo.sh` shows this in the terminal. For a testnet deployment, use the explorer, `cast` or MetaMask.
4. Run `python3 scripts/deployment.py verify` with the deploy and attest transaction hashes. It reads both receipts back, checks the on-chain code against the build, and shows that `latest(network)` holds the same digest.

## 6. Tests and safety (2:30 to 2:45)

Run `python3 -m unittest discover -s tests -t .` and `cd contracts && npm test`. Then show the read-only method allowlist in `potwatch/rpc.py`.

## 7. Closing (2:45 to 2:55)

Show the roadmap slide and the GitHub address, https://github.com/sliarsgard/potwatch.
