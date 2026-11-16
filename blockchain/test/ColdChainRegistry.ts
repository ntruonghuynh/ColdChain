import { expect } from "chai";
import { ethers } from "hardhat";

describe("ColdChainRegistry", function () {
  async function setup() {
    const [admin, shipper, carrier, quality, warehouse, monitor, stranger] = await ethers.getSigners();
    const factory = await ethers.getContractFactory("ColdChainRegistry");
    const registry = await factory.deploy(admin.address, shipper.address, carrier.address,
      quality.address, warehouse.address, monitor.address);
    const id = (value: string) => ethers.keccak256(ethers.toUtf8Bytes(value));
    return { registry, admin, shipper, carrier, quality, warehouse, monitor, stranger, id };
  }

  it("registers, accepts custody, anchors, opens incident, and records authorized disposition/release", async function () {
    const { registry, shipper, carrier, quality, warehouse, monitor, id } = await setup();
    const shipment = id("shipment-1"), policy = id("policy-v1"), data = id("payload");
    await registry.connect(shipper).registerShipment(id("register"), shipment, data, policy);
    await registry.connect(carrier).acceptCustody(id("pickup"), shipment, data, false);
    await registry.connect(carrier).anchorSensorBatch(id("batch"), shipment, data);
    const incident = id("incident");
    await registry.connect(monitor).openIncident(incident, shipment, data);
    await registry.connect(warehouse).acceptCustody(id("delivery"), shipment, data, true);
    await registry.connect(quality).recordDisposition(id("decision"), shipment, data, policy, true, [incident]);
    await registry.connect(warehouse).recordWarehouseRelease(id("release"), shipment, data);
    expect((await registry.shipments(shipment)).state).to.equal(6);
  });

  it("rejects unauthorized roles and invalid transitions", async function () {
    const { registry, shipper, carrier, stranger, id } = await setup();
    const shipment = id("shipment-2"), data = id("payload"), policy = id("policy");
    await expect(registry.connect(stranger).registerShipment(id("r"), shipment, data, policy))
      .to.be.revertedWithCustomError(registry, "Unauthorized");
    await expect(registry.connect(carrier).acceptCustody(id("pickup"), shipment, data, false))
      .to.be.revertedWithCustomError(registry, "InvalidTransition");
    await registry.connect(shipper).registerShipment(id("r"), shipment, data, policy);
    await expect(registry.connect(carrier).acceptCustody(id("pickup"), shipment, data, false))
      .not.to.be.reverted;
    await expect(registry.connect(carrier).acceptCustody(id("pickup2"), shipment, data, false))
      .to.be.revertedWithCustomError(registry, "InvalidTransition");
  });

  it("rejects duplicate references and an incomplete incident disposition", async function () {
    const { registry, shipper, carrier, quality, warehouse, monitor, id } = await setup();
    const shipment = id("shipment-3"), data = id("payload"), policy = id("policy");
    await registry.connect(shipper).registerShipment(id("r"), shipment, data, policy);
    await expect(registry.connect(shipper).registerShipment(id("r"), id("other"), data, policy))
      .to.be.revertedWithCustomError(registry, "DuplicateReference");
    await registry.connect(carrier).acceptCustody(id("pickup"), shipment, data, false);
    const incident = id("incident");
    await registry.connect(monitor).openIncident(incident, shipment, data);
    await registry.connect(warehouse).acceptCustody(id("delivery"), shipment, data, true);
    await expect(registry.connect(quality).recordDisposition(id("d"), shipment, data, policy, true, []))
      .to.be.revertedWithCustomError(registry, "MissingOpenIncident");
    await expect(registry.connect(warehouse).recordWarehouseRelease(id("release"), shipment, data))
      .to.be.revertedWithCustomError(registry, "InvalidTransition");
  });

  it("rejects unknown role grants and repeated submissions", async function () {
    const { registry, admin, shipper, stranger, id } = await setup();
    await expect(registry.connect(admin).grantRole(id("UNKNOWN_ROLE"), stranger.address))
      .to.be.revertedWithCustomError(registry, "Unauthorized");
    const shipment = id("shipment-4"), data = id("payload"), policy = id("policy");
    await registry.connect(shipper).registerShipment(id("registration"), shipment, data, policy);
    await expect(registry.connect(shipper).registerShipment(id("registration"), shipment, data, policy))
      .to.be.revertedWithCustomError(registry, "DuplicateReference");
  });

  it("rejects zero and duplicate role assignments at construction", async function () {
    const [admin, shipper, carrier, quality, warehouse] = await ethers.getSigners();
    const factory = await ethers.getContractFactory("ColdChainRegistry");
    await expect(factory.deploy(ethers.ZeroAddress, shipper.address, carrier.address,
      quality.address, warehouse.address, (await ethers.getSigners())[5].address))
      .to.be.revertedWithCustomError(factory, "Unauthorized");
    await expect(factory.deploy(admin.address, shipper.address, carrier.address,
      quality.address, warehouse.address, admin.address))
      .to.be.revertedWithCustomError(factory, "Unauthorized");
  });

  it("enforces QUALITY disposition, WAREHOUSE release, and shipment-bound incidents", async function () {
    const { registry, shipper, carrier, quality, warehouse, monitor, stranger, id } = await setup();
    const payload = id("payload"), policy = id("policy");
    const shipmentA = id("shipment-a"), shipmentB = id("shipment-b");
    await registry.connect(shipper).registerShipment(id("register-a"), shipmentA, payload, policy);
    await registry.connect(carrier).acceptCustody(id("pickup-a"), shipmentA, payload, false);
    await registry.connect(warehouse).acceptCustody(id("delivery-a"), shipmentA, payload, true);
    await registry.connect(shipper).registerShipment(id("register-b"), shipmentB, payload, policy);
    await registry.connect(carrier).acceptCustody(id("pickup-b"), shipmentB, payload, false);
    await registry.connect(warehouse).acceptCustody(id("delivery-b"), shipmentB, payload, true);
    const incidentA = id("incident-a");
    await registry.connect(monitor).openIncident(incidentA, shipmentA, payload);
    await expect(registry.connect(quality).recordDisposition(id("bad-cross-shipment"), shipmentB,
      payload, policy, true, [incidentA])).to.be.revertedWithCustomError(registry, "ShipmentMismatch");
    await expect(registry.connect(stranger).recordDisposition(id("unauthorized-decision"), shipmentB,
      payload, policy, true, [])).to.be.revertedWithCustomError(registry, "Unauthorized");
    await registry.connect(quality).recordDisposition(id("approved-decision"), shipmentB,
      payload, policy, true, []);
    await expect(registry.connect(stranger).recordWarehouseRelease(id("unauthorized-release"), shipmentB, payload))
      .to.be.revertedWithCustomError(registry, "Unauthorized");
    await expect(registry.connect(warehouse).recordWarehouseRelease(id("approved-release"), shipmentB, payload))
      .not.to.be.reverted;
  });
});
