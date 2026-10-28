// Keyless local test of HealthAttestation: runs the bytecode in an in-memory EVM via
// @ethereumjs/evm runCall. No private keys, no signatures, no network.
// Usage: NODE_PATH=... node contracts/test_contract.mjs  (needs @ethereumjs/evm, @ethereumjs/util)
import { createRequire } from "module";
import fs from "fs";
const require = createRequire(process.env.NODE_PATH + "/");
const { EVM } = require("@ethereumjs/evm");
const { Address, hexToBytes, bytesToHex } = require("@ethereumjs/util");
const { Common, Hardfork, Chain } = require("@ethereumjs/common");

const art = JSON.parse(fs.readFileSync(new URL("./build/HealthAttestation.json", import.meta.url)));
const sel = (sig) => art.methodIdentifiers[sig];
const word = (x) => BigInt(x).toString(16).padStart(64, "0");
const b32 = (s) => Buffer.from(s.padEnd(32, "\0")).toString("hex");
const addr = (n) => new Address(hexToBytes("0x" + n.toString(16).padStart(40, "0")));
const owner = addr(0xa11ce), stranger = addr(0xb0b), bot = addr(0xc0ffee);

const common = new Common({ chain: Chain.Mainnet, hardfork: Hardfork.Paris });
const evm = await EVM.create({ common });
let pass = 0;
const ok = (c, m) => { if (!c) { console.error("FAIL", m); process.exit(1); } pass++; console.log("ok -", m); };

const dep = await evm.runCall({ caller: owner, data: hexToBytes(art.bytecode), gasLimit: 5_000_000n });
ok(!dep.execResult.exceptionError, "deploys");
const to = dep.createdAddress;
const call = (caller, data) => evm.runCall({ caller, to, data: hexToBytes("0x" + data), gasLimit: 1_000_000n });
const net = b32("portaldot-v3-testnet");
const digest = "ab".repeat(32);
const attest = (who, takenAt, sev) => call(who,
  sel("attest(bytes32,bytes32,uint64,uint64,uint64,uint8)") + digest + net + word(232115) + word(232113) + word(takenAt) + word(sev));

let r = await call(stranger, sel("owner()"));
ok(bytesToHex(r.execResult.returnValue).endsWith(owner.toString().slice(2)), "owner is deployer");
r = await attest(stranger, 1000, 3);
ok(!!r.execResult.exceptionError, "stranger cannot attest");
r = await attest(owner, 1000, 3);
ok(!r.execResult.exceptionError, "owner attests (gas " + r.execResult.executionGasUsed + ")");
ok(r.execResult.logs.length === 1, "emits Attested");
r = await attest(owner, 1000, 2);
ok(!!r.execResult.exceptionError, "rejects stale/duplicate takenAt");
r = await call(stranger, sel("setReporter(address,bool)") + word(BigInt(bot.toString())) + word(1));
ok(!!r.execResult.exceptionError, "stranger cannot add reporter");
r = await call(owner, sel("setReporter(address,bool)") + word(BigInt(bot.toString())) + word(1));
ok(!r.execResult.exceptionError, "owner adds reporter");
r = await attest(bot, 2000, 1);
ok(!r.execResult.exceptionError, "new reporter attests");
r = await call(stranger, sel("count()"));
ok(BigInt(bytesToHex(r.execResult.returnValue)) === 2n, "count == 2");
r = await call(stranger, sel("latest(bytes32)") + net);
const ret = bytesToHex(r.execResult.returnValue).slice(2);
ok(ret.slice(0, 64) === digest, "latest digest matches");
ok(BigInt("0x" + ret.slice(64 * 4, 64 * 5)) === 2000n, "latest takenAt is the newer report");
ok(BigInt("0x" + ret.slice(64 * 5, 64 * 6)) === 1n, "latest severity Info");
ok(BigInt("0x" + ret.slice(64 * 7, 64 * 8)) === 1n, "found == true");
console.log(`${pass} checks passed`);
