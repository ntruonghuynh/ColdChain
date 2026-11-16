import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { artifacts, ethers } from "hardhat";

async function main() {
  const signers = await ethers.getSigners();
  const index = (name: string, fallback: number) => Number(process.env[name] || fallback);
  const admin = signers[index("CHAIN_ACCOUNT_INDEX_ADMIN", 0)];
  const shipper = signers[index("CHAIN_ACCOUNT_INDEX_SHIPPER", 1)];
  const carrier = signers[index("CHAIN_ACCOUNT_INDEX_CARRIER", 2)];
  const quality = signers[index("CHAIN_ACCOUNT_INDEX_QUALITY", 3)];
  const warehouse = signers[index("CHAIN_ACCOUNT_INDEX_WAREHOUSE", 4)];
  const monitor = signers[index("CHAIN_ACCOUNT_INDEX_MONITOR", 5)];
  if ([admin, shipper, carrier, quality, warehouse, monitor].some((signer) => !signer)) {
    throw new Error("Required local chain signer index is unavailable");
  }
  const network = await ethers.provider.getNetwork();
  const outputDir = process.env.CHAIN_DEPLOYMENT_DIR || path.resolve("deployments");
  await mkdir(outputDir, { recursive: true });
  const deploymentPath = path.join(outputDir, "local.json");
  try {
    const old = JSON.parse(await readFile(deploymentPath, "utf8"));
    const oldAddress = ethers.getAddress(old.contract_address);
    const oldCode = await ethers.provider.getCode(oldAddress);
    if (Number(old.chain_id) === Number(network.chainId) && oldCode !== "0x") {
      console.log(`ColdChainRegistry already deployed at ${oldAddress} on chain ${network.chainId}`);
      return;
    }
  } catch { /* missing or stale deployment metadata: deploy the contract below */ }
  const factory = await ethers.getContractFactory("ColdChainRegistry", admin);
  const artifact = await artifacts.readArtifact("ColdChainRegistry");
  const registry = await factory.deploy(admin.address, shipper.address, carrier.address,
    quality.address, warehouse.address, monitor.address);
  await registry.waitForDeployment();
  const address = await registry.getAddress();
  await writeFile(deploymentPath, JSON.stringify({
    chain_id: Number(network.chainId), contract_address: address,
    deployed_at: new Date().toISOString(), abi: artifact.abi, roles: {
      ADMIN: admin.address, SHIPPER: shipper.address, CARRIER: carrier.address,
      QUALITY: quality.address, WAREHOUSE: warehouse.address, MONITOR: monitor.address,
    },
    security_note: "Hardhat development mnemonic only. No production or customer value.",
  }, null, 2) + "\n", { mode: 0o644 });
  console.log(`ColdChainRegistry deployed at ${address} on chain ${network.chainId}`);
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
