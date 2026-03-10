/**
 * capture-templates.mjs — One-time template capture script.
 *
 * Run inside the container to regenerate the persistent template PNGs
 * committed to assets/.  This is a standalone Node.js script:
 *
 *   node capture-templates.mjs
 *
 * Full form-group rows are captured (label + input) so the label text
 * disambiguates the username and password fields.  The CTA button is
 * visually distinct from the social login buttons (different color/style).
 *
 * Render baseline: 1280x720 viewport, deviceScaleFactor: 1, Arial font.
 */
import { chromium } from 'playwright';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const assetDir = path.join(__dirname, 'assets');
const pageUrl = 'file://' + path.join(__dirname, 'pages/login.html');

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
});
await page.goto(pageUrl);
await page.evaluate(() => document.fonts.ready);

const groups = await page.locator('.form-group').all();
await groups[0].screenshot({
  path: path.join(assetDir, 'username-field.png'),
  animations: 'disabled',
});
console.log('  captured username-field.png');

await groups[1].screenshot({
  path: path.join(assetDir, 'password-field.png'),
  animations: 'disabled',
});
console.log('  captured password-field.png');

await page.locator('#signin-btn').screenshot({
  path: path.join(assetDir, 'signin-cta.png'),
  animations: 'disabled',
});
console.log('  captured signin-cta.png');

await browser.close();
console.log('Done — 3 templates written to assets/');
