import { expect, test } from '@playwright/test';
import { vision } from 'check-cep-vision';
import {
  asset,
  DISTRACTOR_TILE_ID,
  MARKETPLACE_URL,
  TARGET_STATUS_ID,
  TARGET_TILE_ID,
  TILE_CLICK_OFFSET,
} from './functions';

test('marketplace page is crowded with many preview tiles', async ({ page }) => {
  await page.goto(MARKETPLACE_URL);
  await page.evaluate(() => document.fonts.ready);

  await expect(page.locator('.market-tile')).toHaveCount(17);
  await expect(page.locator('.promo-chip')).toHaveCount(8);
  await expect(page.locator('.photo-frame')).toHaveCount(17);
  await expect(page.locator('[data-similar-group="dryer"]')).toHaveCount(2);
});

test('small preview screenshot is ambiguous across similar tiles', async ({ page }) => {
  await page.goto(MARKETPLACE_URL);
  await page.evaluate(() => document.fonts.ready);

  const result = await vision.locateByImage(page, asset('aurora-preview-tile.png'), {
    fullPage: true,
    confidence: 0.55,
  });

  expect(result.found).toBe(false);
  expect(result.reason).toContain('ambig');
});

test('finds the intended article by a small preview screenshot', async ({ page }) => {
  await page.goto(MARKETPLACE_URL);
  await page.evaluate(() => document.fonts.ready);

  const previewLocator = page.locator(TARGET_TILE_ID + ' .preview-crop');
  await previewLocator.scrollIntoViewIfNeeded();

  const targetBox = await previewLocator.boundingBox();
  expect(targetBox).not.toBeNull();

  const targetRegion = {
    x: Math.floor(targetBox!.x - 12),
    y: Math.floor(targetBox!.y - 12),
    width: Math.ceil(targetBox!.width + 24),
    height: Math.ceil(targetBox!.height + 24),
  };

  await vision.clickByImage(page, asset('aurora-preview-tile.png'), {
    region: targetRegion,
    confidence: 0.82,
    clickOffset: TILE_CLICK_OFFSET,
    debugDir: '/home/pwuser/results/debug',
    debugLabel: 'preview-tile-match',
  });

  await expect(page.locator('body')).toHaveAttribute('data-opened-item', 'aurora-hairdryer');
  await expect(page.locator(TARGET_TILE_ID)).toHaveAttribute('data-opened', 'true');
  await expect(page.locator(TARGET_STATUS_ID)).toHaveText('Opened');
  await expect(page.locator(DISTRACTOR_TILE_ID)).not.toHaveAttribute('data-opened', 'true');
  await expect(page.locator('#detail-panel')).toContainText('Aurora Ionic Hair Dryer');
});
