/**
 * capture-templates.mjs — One-time template capture script.
 *
 * Run inside the container to regenerate the persistent template PNGs
 * committed to assets/.  This is a standalone Node.js script (not a
 * Playwright test) — run it directly with node:
 *
 *   node capture-templates.mjs
 *
 * Each template captures a full field row (label + input) so the label
 * text disambiguates identical-looking input fields.  The submit button
 * is captured as a standalone element.
 *
 * Render baseline: 1280x720 viewport, deviceScaleFactor: 1, Arial font.
 */
import { chromium } from 'playwright';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const assetDir = path.join(__dirname, 'assets');
const pageUrl = 'file://' + path.join(__dirname, 'pages/form.html');

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
});
await page.goto(pageUrl);
await page.evaluate(() => document.fonts.ready);

// Field-row templates: label + input together
for (const [id, name] of [
  ['#row-name', 'name-row'],
  ['#row-prename', 'prename-row'],
  ['#row-city', 'city-row'],
]) {
  await page.locator(id).screenshot({
    path: path.join(assetDir, `${name}.png`),
    animations: 'disabled',
  });
  console.log(`  captured ${name}.png`);
}

// Submit button
await page.locator('#submit-btn').screenshot({
  path: path.join(assetDir, 'submit-btn.png'),
  animations: 'disabled',
});
console.log('  captured submit-btn.png');

await browser.close();
console.log('Done — 4 templates written to assets/');
