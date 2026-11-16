# Local blockchain registry (M5)

This Hardhat project runs a disposable local chain and deploys
`ColdChainRegistry`. Docker Compose starts the chain, waits for its JSON-RPC
health check, deploys the contract to a shared deployment volume, and then starts
the API and outbox worker. The worker reads the deployed ABI/address and signs
business actions with local role-specific accounts.

## Local checks

```bash
npm ci
npx hardhat compile
npx hardhat test
```

For a host-local node and deployment, start `npx hardhat node` in one terminal,
then run:

```bash
CHAIN_RPC_URL=http://127.0.0.1:8545 npx hardhat run scripts/deploy.ts --network localhost
```

The deployment file contains the contract ABI, local role addresses and chain
id. In Compose it is written to the `chain-deployments` volume and mounted
read-only into the backend and worker. A repeated deploy on the same live chain
reuses the existing contract when its code is present.

Hardhat uses public test accounts with no real value. Do not connect the demo
mnemonic to a public network. The chain is in-memory: recreating the node loses
its state. The deployment volume is metadata only; see the recovery limits in
[`docs/design/m5-blockchain-workflow.md`](../docs/design/m5-blockchain-workflow.md).

Role/action assignments: [`ROLES.md`](ROLES.md). Acceptance evidence:
[`docs/milestones/m5/README.md`](../docs/milestones/m5/README.md).
