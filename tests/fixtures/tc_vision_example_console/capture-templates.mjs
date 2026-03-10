/**
 * capture-templates.mjs — One-time template capture script.
 *
 * Run inside the container to regenerate the persistent template PNG
 * committed to assets/.  This is a standalone Node.js script:
 *
 *   node capture-templates.mjs
 *
 * Only one template is needed: a single "Delete job" button.  All six
 * buttons on the page are visually identical, which is the point —
 * the test demonstrates ambiguity rejection and region-guided resolution.
 *
 * Render baseline: 1280x720 viewport, deviceScaleFactor: 1, Arial font.
 */
import { chromium } from 'playwright';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const assetDir = path.join(__dirname, 'assets');
const pageUrl = 'file://' + path.join(__dirname, 'pages/console.html');

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
});
await page.goto(pageUrl);
await page.evaluate(() => document.fonts.ready);

await page.locator('#delete-left-1').screenshot({
  path: path.join(assetDir, 'delete-btn.png'),
  animations: 'disabled',
});
console.log('  captured delete-btn.png');

await browser.close();
console.log('Done — 1 template written to assets/');
