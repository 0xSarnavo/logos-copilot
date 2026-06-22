# Recipe: Run a local Logos Blockchain (Nomos / Cryptarchia) node

**Component:** `logos-blockchain` (formerly Nomos). Consensus = **Cryptarchia / Proof-of-Leadership (PoL)**.

## Build & run
```bash
git clone https://github.com/logos-blockchain/logos-blockchain
cd logos-blockchain
cargo build -p logos-blockchain-node --release
# run with a node config (see node-config examples in the repo); HTTP API serves on :8080
```

## HTTP API — endpoints confirmed working today (base `http://localhost:8080`)
| Method | Path | Returns |
|---|---|---|
| GET | `/cryptarchia/info` | height, slot, lib_slot, lib hash, tip hash, mode |
| GET | `/cryptarchia/headers` | recent block-header hashes |
| GET | `/network/info` | peer_id, n_peers, n_connections, listen addrs |
| GET | `/wallet/{key}/balance` | balance + UTXO notes (key is a **public** 64-hex account id) |
| POST | `/storage/block` | decoded block content (JSON body = block hash) |

> Endpoints like `/mempool/*`, `/cryptarchia/block/{hash}`, `/network/peers`, `/da/status`,
> `/metrics`, and `WS /subscribe/blocks` are **not yet exposed** — don't depend on them.

## Get testnet funds
```bash
curl -X POST https://testnet.blockchain.logos.co/web/faucet-backend/<your-wallet-key>
```

## Critical correctness notes
- **`leader_key` in a block is an ephemeral per-block PoL lottery key — NOT a wallet/identity.**
  A fresh, unlinkable key per block. Never treat it as an operator address.
- `wallet/{key}/balance` keys are **public** account identifiers, not private signing keys.

## Sources
- `logos-blockchain/logos-blockchain`, `logos-blockchain/logos-blockchain-specs`
- `logos-blockchain/logos-blockchain-block-explorer-template` (the node's intended streaming API)
