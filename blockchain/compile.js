// Reproducible build: `npm install solc@0.8.24` then `node blockchain/compile.js blockchain/contracts/CredentialAnchor.sol blockchain/build/CredentialAnchor.json`
const solc = require("solc"), fs = require("fs"), path = process.argv[2], out = process.argv[3];
const input = { language: "Solidity", sources: { "CredentialAnchor.sol": { content: fs.readFileSync(path, "utf8") } },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "paris", outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } } } };
const result = JSON.parse(solc.compile(JSON.stringify(input)));
(result.errors || []).forEach(e => console.error(e.formattedMessage));
if ((result.errors || []).some(e => e.severity === "error")) process.exit(1);
const c = result.contracts["CredentialAnchor.sol"].CredentialAnchor;
fs.writeFileSync(out, JSON.stringify({ contractName: "CredentialAnchor", compiler: "solc " + solc.version(), evmVersion: "paris", optimizer: { enabled: true, runs: 200 }, abi: c.abi, bytecode: "0x" + c.evm.bytecode.object }, null, 2) + "\n");
console.log("compiled with", solc.version(), "bytecode bytes:", c.evm.bytecode.object.length / 2);
