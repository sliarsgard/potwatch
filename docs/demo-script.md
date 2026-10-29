# Demo video script (under 3 minutes)

Recording: screen capture of a terminal and a browser, with voice-over or captions. The bracketed times are targets.

1. **[0:00–0:15] Hook.** Show the title slide. "potwatch tells you when a Portaldot network is unhealthy, why, and lets you prove it on-chain."
2. **[0:15–0:50] One command.** Run `python3 -m potwatch check --history 120 --out out/`. Scroll the text output for both networks and point at the CRIT/WARN lines and their hints. Show `echo $?`, which prints 2 when there is a critical finding (cron/CI friendly).
3. **[0:50–1:20] The report.** Open `out/report.html`. Show the block-time chart, the per-author split, and the cross-network key-reuse finding.
4. **[1:20–1:35] Monitoring.** Show `cat out/metrics.prom | head` and `python3 -m potwatch watch --iterations 2 --interval 10`.
5. **[1:35–2:30] On-chain.**
   - Run `python3 -m potwatch digest --report out/report.json`.
   - Run `python3 scripts/attest_calldata.py out/report.json --contract <address>`.
   - In the explorer (or with `cast`/MetaMask), show the deployed `HealthAttestation` contract and the `attest` transaction, with the same digest in the `Attested` event.
   - Call `latest(network)` and show that the digest matches.
6. **[2:30–2:50] Tests and safety.** Run `python3 -m unittest discover -s tests -t .` and `cd contracts && npm test`. Show the read-only allowlist in `potwatch/rpc.py`.
7. **[2:50–3:00] Close.** Show the roadmap slide and the GitHub URL.
