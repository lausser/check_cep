import { mkdir } from 'node:fs/promises';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const assetDir = path.join(__dirname, 'assets');
const pageUrl = 'file://' + path.join(__dirname, 'pages/news.html');

await mkdir(assetDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
});

await page.goto(pageUrl);
await page.evaluate(() => document.fonts.ready);

await page.locator('#lead-story-button').screenshot({
  path: path.join(assetDir, 'story-btn.png'),
  animations: 'disabled',
});

await page.locator('#accept-cookies').screenshot({
  path: path.join(assetDir, 'accept-btn.png'),
  animations: 'disabled',
});

await browser.close();
console.log('Done - 2 templates written to assets/');
