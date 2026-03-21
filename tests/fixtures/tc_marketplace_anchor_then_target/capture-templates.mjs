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

await page.locator('#tile-aurora-supersonic .preview').screenshot({
  path: path.join(assetDir, 'aurora-preview.png'),
  animations: 'disabled',
});

await page.locator('#aurora-anchor-badge').screenshot({
  path: path.join(assetDir, 'night-sale-badge.png'),
  animations: 'disabled',
});

await browser.close();
console.log('Done - 2 templates written to assets/');
