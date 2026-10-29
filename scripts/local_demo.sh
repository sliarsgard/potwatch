#!/usr/bin/env bash
# End-to-end demo on a local anvil chain: preflight, deploy, attest a fresh potwatch report, verify --write.
# Uses only anvil's public, unlocked dev account 0 via eth_sendTransaction; no private key is passed anywhere.
set -euo pipefail
cd "$(dirname "$0")/.."

RPC=${RPC:-http://127.0.0.1:8545}
FROM=${FROM:-0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266}
NETS=networks.local.json
NET=local-anvil
OUT=${OUT:-out/local-demo}

case "$RPC" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *) echo "refusing to send transactions to non-local RPC $RPC" >&2; exit 1 ;;
esac
[ "$(cast chain-id --rpc-url "$RPC")" = 420420777 ] || { echo "start anvil with --chain-id 420420777" >&2; exit 1; }

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

step "1/5 preflight (read-only dry-run of the constructor)"
python3 scripts/deployment.py --networks "$NETS" --network "$NET" preflight --from "$FROM"

step "2/5 deploy contracts/build/HealthAttestation.json"
DEPLOY_TX=$(cast send --rpc-url "$RPC" --unlocked --from "$FROM" --json \
  --create "$(jq -r .bytecode contracts/build/HealthAttestation.json)" | jq -r .transactionHash)
CONTRACT=$(cast receipt --rpc-url "$RPC" "$DEPLOY_TX" contractAddress)
echo "deploy tx $DEPLOY_TX"
echo "contract  $CONTRACT"

step "3/5 potwatch check of the public V3 testnet (read-only)"
if [ -n "${REPORT:-}" ]; then
  echo "using existing report $REPORT"
else
  python3 -m potwatch check --network portaldot-v3-testnet --history 120 --out "$OUT" || true
  REPORT=$OUT/report.json
fi

step "4/5 attest the report digest on the local chain"
CALLDATA=$(python3 scripts/attest_calldata.py "$REPORT" --contract "$CONTRACT" | jq -r '.[0].calldata')
python3 scripts/attest_calldata.py "$REPORT" --contract "$CONTRACT" | jq '.[0] | del(.calldata)'
ATTEST_TX=$(cast send --rpc-url "$RPC" --unlocked --from "$FROM" --json "$CONTRACT" "$CALLDATA" | jq -r .transactionHash)
echo "attest tx $ATTEST_TX"

step "5/5 verify from receipts and record (verify --write)"
python3 scripts/deployment.py --networks "$NETS" --network "$NET" verify \
  --deploy-tx "$DEPLOY_TX" --attest-tx "$ATTEST_TX" --write ${WRITE_EXTRA:-}
echo
echo "count() on-chain: $(cast call --rpc-url "$RPC" "$CONTRACT" "count()(uint256)")"
python3 -m potwatch digest --report "$REPORT" | head -5
