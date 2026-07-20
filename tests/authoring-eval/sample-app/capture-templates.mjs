// Capture tight image-template crops for the vision-fallback probes.
// Run offline:  NODE_PATH=<container node_modules> node capture-templates.mjs
// The crops are solid, font-independent canvas shapes, so they match
// deterministically across host/container rendering.
import { chromium } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import * as path from 'node:path';

const here = path.dirname(new URL(import.meta.url).pathname);

async function crop(relHtml, selector, outPath) {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.goto(pathToFileURL(path.join(here, relHtml)).href);
  const el = page.locator(selector);
  await el.waitFor();
  // Let the inline canvas-drawing script paint before cropping.
  await page.waitForTimeout(200);
  await el.screenshot({ path: outPath });
  await browser.close();
  console.log('wrote', outPath);
}

await crop(
  'probes/no-stable-locator/index.html',
  '#panel canvas',
  path.join(here, 'probes/no-stable-locator/assets/play-icon.png'),
);
await crop(
  'probes/moving-element/index.html',
  '#target',
  path.join(here, 'probes/moving-element/assets/badge.png'),
);
