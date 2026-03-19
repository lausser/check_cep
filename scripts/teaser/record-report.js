#!/usr/bin/env node
/**
 * record-report.js — Record Playwright HTML report navigation as video.
 *
 * Starts a local HTTP server for the report, opens it in Playwright,
 * navigates to a specific test, and records the session as video.
 *
 * Usage:
 *   node record-report.js --report-dir /path/to/playwright-report \
 *                          --video-dir /path/to/output \
 *                          --test-name "teaser pass" \
 *                          [--show-errors]
 *
 * Designed to run inside the check_cep container (Playwright + Python available).
 */
const { chromium } = require('playwright');
const { execSync, spawn } = require('child_process');
const path = require('path');

// Parse CLI args
const args = process.argv.slice(2);
function getArg(name) {
  const idx = args.indexOf(name);
  return idx >= 0 && idx + 1 < args.length ? args[idx + 1] : null;
}
const reportDir = getArg('--report-dir');
const videoDir = getArg('--video-dir');
const testName = getArg('--test-name');
const showErrors = args.includes('--show-errors');

if (!reportDir || !videoDir || !testName) {
  console.error('Usage: node record-report.js --report-dir DIR --video-dir DIR --test-name NAME [--show-errors]');
  process.exit(1);
}

const PORT = 9323;

(async () => {
  // Start HTTP server in background
  const server = spawn('python3', ['-m', 'http.server', String(PORT), '--directory', reportDir], {
    stdio: 'ignore',
    detached: true,
  });
  server.unref();

  // Wait for server to be ready
  let retries = 20;
  while (retries-- > 0) {
    try {
      execSync(`curl -s -o /dev/null http://localhost:${PORT}/`, { timeout: 2000 });
      break;
    } catch {
      await new Promise(r => setTimeout(r, 500));
    }
  }
  if (retries < 0) {
    console.error('ERROR: HTTP server did not start');
    process.kill(-server.pid);
    process.exit(1);
  }

  try {
    const browser = await chromium.launch({
      headless: true,
      args: ['--disable-gpu', '--no-sandbox'],
    });
    const context = await browser.newContext({
      recordVideo: { dir: videoDir, size: { width: 1280, height: 720 } },
      viewport: { width: 1280, height: 720 },
    });
    const page = await context.newPage();

    // Navigate to report
    await page.goto(`http://localhost:${PORT}/`);
    await page.waitForSelector('.test-file-test', { timeout: 15000 });
    await page.waitForTimeout(1500);

    // Click on the test by name
    const testLink = page.locator('.test-file-title', { hasText: testName });
    await testLink.click();

    // Wait for test detail view to render
    await page.waitForSelector('.tree-item', { timeout: 10000 });
    await page.waitForTimeout(2000);

    if (showErrors) {
      // Scroll to and expand the Errors section
      const errorsChip = page.locator('.chip-header', { hasText: 'Errors' });
      if (await errorsChip.count() > 0) {
        await errorsChip.scrollIntoViewIfNeeded();
        await page.waitForTimeout(500);
        // Click to expand if collapsed
        const expanded = await errorsChip.getAttribute('class');
        if (expanded && expanded.includes('expanded-false')) {
          await errorsChip.click();
          await page.waitForTimeout(500);
        }
        await page.waitForTimeout(2500);

        // Scroll down stepwise to the failure screenshot so the viewer
        // sees it's on the same page, just further below.
        const screenshotImg = page.locator('img.screenshot').first();
        if (await screenshotImg.count() > 0) {
          const targetY = await screenshotImg.evaluate(el => {
            const rect = el.getBoundingClientRect();
            // Scroll until the bottom of the image is visible with some padding
            return window.scrollY + rect.bottom - window.innerHeight + 40;
          });
          let currentY = await page.evaluate(() => window.scrollY);
          const step = 50;
          while (currentY < targetY) {
            currentY = Math.min(currentY + step, targetY);
            await page.evaluate(y => window.scrollTo(0, y), currentY);
            await page.waitForTimeout(80);
          }
          await page.waitForTimeout(3000);
        }
      }
    } else {
      // For passing tests, just pause so viewer can see the steps
      await page.waitForTimeout(2000);
    }

    await context.close(); // finalizes the video
    await browser.close();
  } finally {
    // Stop the HTTP server
    try { process.kill(-server.pid); } catch { /* already dead */ }
  }
})();
