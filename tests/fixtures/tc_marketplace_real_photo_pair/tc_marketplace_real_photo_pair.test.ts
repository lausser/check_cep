import { expect, test } from '@playwright/test';
import { vision } from 'check-cep-vision';
import {
  asset,
  DISTRACTOR_TILE_ID,
  MARKETPLACE_URL,
  PREVIEW_CLICK_OFFSET,
  TARGET_STATUS_ID,
  TARGET_TILE_ID,
} from './functions';

test('small real-photo preview crop is ambiguous across the dryer pair', async ({ page }) => {
  await page.goto(MARKETPLACE_URL);
  await page.evaluate(() => document.fonts.ready);

  await expect(page.locator('[data-similar-group="dryer"]')).toHaveCount(2);

  const result = await vision.locateByImage(page, asset('dryer-ambiguous-crop.png'), {
    fullPage: true,
    confidence: 0.5,
    ambiguityGap: 0.05,
  });

  expect(result.found).toBe(false);
  expect(result.reason).toContain('ambig');
});

test('card-scoped matching opens only the intended real-photo item', async ({ page }) => {
  await page.goto(MARKETPLACE_URL);
  await page.evaluate(() => document.fonts.ready);
  await page.locator(TARGET_TILE_ID).scrollIntoViewIfNeeded();

  const previewBox = await page.locator(TARGET_TILE_ID + ' .preview').boundingBox();
  expect(previewBox).not.toBeNull();

  const targetRegion = {
    x: Math.floor(previewBox!.x - 8),
    y: Math.floor(previewBox!.y - 8),
    width: Math.ceil(previewBox!.width + 16),
    height: Math.ceil(previewBox!.height + 16),
  };

  await vision.clickByImage(page, asset('dryer-ambiguous-crop.png'), {
    region: targetRegion,
    confidence: 0.56,
    ambiguityGap: 0.05,
    clickOffset: PREVIEW_CLICK_OFFSET,
    debugDir: '/home/pwuser/results/debug',
    debugLabel: 'real-photo-dryer-preview',
  });

  await expect(page.locator('body')).toHaveAttribute('data-opened-item', 'salon-air-01');
  await expect(page.locator(TARGET_TILE_ID)).toHaveAttribute('data-opened', 'true');
  await expect(page.locator(TARGET_STATUS_ID)).toHaveText('Opened');
  await expect(page.locator(DISTRACTOR_TILE_ID)).not.toHaveAttribute('data-opened', 'true');
  await expect(page.locator('#detail-panel')).toContainText('Salon Air Dryer 01');
});
