import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from '/private/tmp/coldchain-m3-playwright/node_modules/playwright/index.mjs';

const baseURL = 'http://localhost:3000';
const shipmentId = 'SIM-S11-J0154';
const beforeRestore = '2026-10-19T15:57:03Z';
const afterRestore = '2026-10-19T23:02:00Z';
const evidenceDir = new URL('../screenshots/', import.meta.url);
await mkdir(evidenceDir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath:
    '/Users/huynhnamtruong/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  args: ['--no-sandbox'],
});

const results = {
  browser: await browser.version(),
  scenario: { shipmentId, beforeRestore, afterRestore },
  viewports: {},
};

async function runViewport(name, viewport, isMobile = false) {
  const context = await browser.newContext({ viewport, isMobile, deviceScaleFactor: 1, timezoneId: 'UTC' });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const badResponses = [];
  const telemetryPayloads = [];

  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('requestfailed', (request) => failedRequests.push({ url: request.url(), error: request.failure()?.errorText }));
  page.on('response', async (response) => {
    if (response.status() >= 400) badResponses.push({ url: response.url(), status: response.status() });
    if (response.url().includes(`/api/shipments/${shipmentId}/telemetry`)) {
      try {
        telemetryPayloads.push((await response.json()).data);
      } catch {
        // A malformed response is reported by the UI assertion and kept in the response log.
      }
    }
  });

  await page.goto(`${baseURL}/temperature`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Temperature Monitoring' }).waitFor();
  await page.locator('select').selectOption(shipmentId);
  const asOfInput = page.getByLabel('View as of (UTC, processing time)');

  await asOfInput.fill(beforeRestore.replace('Z', ''));
  await page.getByRole('button', { name: 'Apply' }).click();
  await page.waitForURL((url) => url.searchParams.get('as_of') === beforeRestore);
  const statusPanel = page.getByRole('region', { name: 'Monitoring status in plain language' });
  const chart = page.getByRole('img', { name: /Temperature of sensor SIM-S11-L0154/ });
  await chart.waitFor();
  await page.getByText('2026-10-19 08:53 UTC').waitFor();
  const beforePayload = telemetryPayloads.at(-1);
  assert.ok(beforePayload, `${name}: pre-restore telemetry response captured`);
  const beforeSensor = beforePayload.sensors[0];
  assert.equal(beforePayload.as_of, beforeRestore);
  assert.equal(beforeSensor.readings.length, 315);
  assert.ok(beforeSensor.readings.every((reading) => reading.received_at <= beforeRestore), 'no future receipt is shown before restore');
  assert.ok(beforeSensor.runs.every((run) => run.raised_at <= beforeRestore), 'no future detection is shown before restore');
  assert.equal(beforeSensor.status.state, 'UNKNOWN');
  assert.equal(beforeSensor.status.communication.status, 'LONGER_THAN_RECENT_UPLOAD_INTERVALS');
  assert.deepEqual(beforeSensor.status.open_incidents_as_of, { TEMPERATURE_EXCURSION: 0, DATA_GAP: 0 });
  assert.match(await chart.getAttribute('aria-label'), /315 readings, 0 confirmed gaps/);
  assert.match(await statusPanel.innerText(), /Current temperature not known/);
  assert.match(await statusPanel.innerText(), /Possible communication delay or outage/);
  assert.match(await statusPanel.innerText(), /Missing data is never treated as safe/);
  assert.match(await statusPanel.innerText(), /0 temperature excursion\(s\), 0 data-gap incident\(s\)/);
  assert.match((await chart.locator('title').allTextContents()).join(' '), /Not yet received/);
  await page.screenshot({ path: new URL(`e2e-asof-before-${name}.png`, evidenceDir).pathname, fullPage: true });

  await asOfInput.fill(afterRestore.replace('Z', ''));
  await page.getByRole('button', { name: 'Apply' }).click();
  await page.waitForURL((url) => url.searchParams.get('as_of') === afterRestore);
  await page.getByText('2026-10-19 23:01 UTC').waitFor();
  await chart.waitFor();
  const afterPayload = telemetryPayloads.at(-1);
  assert.ok(afterPayload, `${name}: post-restore telemetry response captured`);
  const afterSensor = afterPayload.sensors[0];
  assert.equal(afterPayload.as_of, afterRestore);
  assert.equal(afterSensor.readings.length, 484);
  assert.ok(afterSensor.readings.every((reading) => reading.received_at <= afterRestore), 'no future receipt is shown after restore');
  assert.ok(afterSensor.runs.every((run) => run.raised_at <= afterRestore), 'no future detection is shown after restore');
  assert.equal(afterSensor.status.state, 'CURRENT');
  assert.equal(afterSensor.status.communication.status, 'WITHIN_RECENT_UPLOAD_INTERVALS');
  assert.deepEqual(afterSensor.status.open_incidents_as_of, { TEMPERATURE_EXCURSION: 1, DATA_GAP: 0 });
  assert.match(await chart.getAttribute('aria-label'), /484 readings, 0 confirmed gaps/);
  assert.match(await statusPanel.innerText(), /1 temperature excursion\(s\), 0 data-gap incident\(s\)/);
  assert.doesNotMatch(await statusPanel.innerText(), /temperature is safe|temperature is normal/i);
  assert.match(await statusPanel.innerText(), /last upload 1 min ago|last upload 0 min ago|Waiting for the next scheduled upload/);

  const dimensions = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
  }));
  assert.ok(dimensions.documentWidth <= dimensions.viewportWidth, `${name}: no horizontal page overflow (${JSON.stringify(dimensions)})`);
  await page.screenshot({ path: new URL(`e2e-asof-after-${name}.png`, evidenceDir).pathname, fullPage: true });

  results.viewports[name] = {
    before: {
      asOf: beforePayload.as_of,
      readings: beforeSensor.readings.length,
      newestEventAt: beforeSensor.status.newest_event_at,
      newestReceivedAt: beforeSensor.status.newest_received_at,
      monitoringState: beforeSensor.status.state,
      communicationStatus: beforeSensor.status.communication.status,
      incidents: beforeSensor.status.open_incidents_as_of,
      missingDataMessage: 'Missing data is never treated as safe.',
    },
    after: {
      asOf: afterPayload.as_of,
      readings: afterSensor.readings.length,
      newestEventAt: afterSensor.status.newest_event_at,
      newestReceivedAt: afterSensor.status.newest_received_at,
      monitoringState: afterSensor.status.state,
      communicationStatus: afterSensor.status.communication.status,
      incidents: afterSensor.status.open_incidents_as_of,
    },
    dimensions,
    consoleErrors,
    pageErrors,
    failedRequests,
    badResponses,
  };

  await context.close();
  assert.deepEqual(consoleErrors, [], `${name}: browser console errors`);
  assert.deepEqual(pageErrors, [], `${name}: uncaught page errors`);
  assert.deepEqual(failedRequests, [], `${name}: failed network requests`);
  assert.deepEqual(badResponses, [], `${name}: HTTP error responses`);
}

try {
  await runViewport('desktop', { width: 1440, height: 1000 });
  await runViewport('mobile', { width: 390, height: 844 }, true);
  console.log(JSON.stringify({ result: 'PASS', ...results }, null, 2));
} finally {
  await browser.close();
}
