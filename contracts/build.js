// Compile HealthAttestation.sol with solc-js. evmVersion "paris" avoids PUSH0,
// which older Frontier-based EVMs may not support.
// Usage: cd contracts && npm install && npm run build
const fs = require("fs"), path = require("path"), solc = require("solc");
const src = fs.readFileSync(path.join(__dirname, "HealthAttestation.sol"), "utf8");
const input = { language: "Solidity", sources: { "HealthAttestation.sol": { content: src } },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "paris",
    outputSelection: { "*": { "*": ["abi", "evm.bytecode.object", "evm.methodIdentifiers"] } } } };
const out = JSON.parse(solc.compile(JSON.stringify(input)));
for (const e of out.errors || []) { console.error(e.formattedMessage); if (e.severity === "error") process.exit(1); }
const c = out.contracts["HealthAttestation.sol"].HealthAttestation;
fs.writeFileSync(path.join(__dirname, "build", "HealthAttestation.json"), JSON.stringify({
  compiler: solc.version(), evmVersion: "paris", abi: c.abi,
  bytecode: "0x" + c.evm.bytecode.object, methodIdentifiers: c.evm.methodIdentifiers }, null, 1));
console.log("ok", solc.version(), "bytecode bytes:", c.evm.bytecode.object.length / 2);
console.log(c.evm.methodIdentifiers);
