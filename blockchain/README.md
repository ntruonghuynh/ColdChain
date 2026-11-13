# blockchain/

**Status: not implemented.** Scheduled for Milestone 5.

Planned contents (see `docs/architecture.md` §7.4):

| Path | Purpose |
|---|---|
| `contracts/ColdChainRegistry.sol` | Roles, approval state machine, unique business references, batch hash anchoring |
| `scripts/deploy.ts` | Deploy and grant roles on the local Hardhat network |
| `test/` | Hardhat tests: every function × allowed and forbidden role, invalid transitions, duplicates |
| `ROLES.md` | Role rules for submission (SUB-04) |

Only IDs, hashes, versions and accepted state changes go on chain. Local Hardhat dev accounts are test-only.

Main requirements: BC-01 to BC-14, FR-23, FR-24.
