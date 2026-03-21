import { mkdir } from 'node:fs/promises';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const assetDir = path.join(__dirname, 'assets');
const pageUrl = 'file://' + path.join(__dirname, 'pages/marketplace.html');

await mkdir(assetDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
});

await page.goto(pageUrl);
await page.evaluate(() => document.fonts.ready);

await page.locator('#tile-salon-air-01 .preview').screenshot({
  path: path.join(assetDir, 'dryer-preview.png'),
  animations: 'disabled',
});

await browser.close();
console.log('Done - 1 preview screenshot written to assets/');
