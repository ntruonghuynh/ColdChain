import { performance } from "node:perf_hooks";
import { ethers } from "hardhat";

function quantile(values: number[], q: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(q * sorted.length) - 1)];
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

async function main() {
  const [admin, shipper, carrier, quality, warehouse, monitor] = await ethers.getSigners();
  const factory = await ethers.getContractFactory("ColdChainRegistry", admin);
  const registry = await factory.deploy(admin.address, shipper.address, carrier.address,
    quality.address, warehouse.address, monitor.address);
  await registry.waitForDeployment();
  const id = (value: string) => ethers.keccak256(ethers.toUtf8Bytes(value));
  const shipment = id("m5-benchmark-shipment");
  const policy = id("m5-benchmark-policy");
  const payload = id("m5-benchmark-payload");
  const timings: number[] = [];
  const gasUsed: number[] = [];

  await (await registry.connect(shipper).registerShipment(id("m5-benchmark-registration"), shipment,
    payload, policy)).wait();
  await (await registry.connect(carrier).acceptCustody(id("m5-benchmark-pickup"), shipment,
    payload, false)).wait();
  for (let i = 0; i < 30; i += 1) {
    const started = performance.now();
    const tx = await registry.connect(carrier).anchorSensorBatch(id(`m5-benchmark-batch-${i}`), shipment, payload);
    const receipt = await tx.wait();
    timings.push(performance.now() - started);
    if (!receipt || receipt.status !== 1) throw new Error(`batch ${i} was not mined successfully`);
    gasUsed.push(Number(receipt.gasUsed));
  }
  console.log(JSON.stringify({
    benchmark: "m5-local-chain-submit-and-confirm",
    chain_id: Number((await ethers.provider.getNetwork()).chainId),
    sample_count: timings.length,
    units: "milliseconds",
    accepted: timings.length,
    rejected: 0,
    p50: median(timings),
    p95: quantile(timings, 0.95),
    gas_used_p50: median(gasUsed),
    gas_used_p95: quantile(gasUsed, 0.95),
    gas_used_per_transaction: gasUsed,
    min: Math.min(...timings),
    max: Math.max(...timings),
    timings,
    note: "In-process local Hardhat chain; wall time from submission call to mined receipt; not a production latency estimate.",
  }, null, 2));
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
