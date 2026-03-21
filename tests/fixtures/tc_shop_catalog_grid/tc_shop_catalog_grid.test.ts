import { expect, test } from '@playwright/test';
import { vision } from 'check-cep-vision';
import {
  asset,
  CATALOG_URL,
  DISTRACTOR_CARD_ID,
  TARGET_CARD_ID,
  TARGET_STATUS_ID,
} from './functions';

test('broad add-to-cart search is ambiguous', async ({ page }) => {
  await page.goto(CATALOG_URL);
  await page.evaluate(() => document.fonts.ready);

  const result = await vision.locateByImage(page, asset('add-btn.png'), {
    region: 'main',
    confidence: 0.35,
  });

  expect(result.found).toBe(false);
  expect(result.reason).toContain('ambig');
});

test('card-scoped search adds only the intended product', async ({ page }) => {
  await page.goto(CATALOG_URL);
  await page.evaluate(() => document.fonts.ready);
  await page.locator(TARGET_CARD_ID).scrollIntoViewIfNeeded();

  const targetBox = await page.locator(TARGET_CARD_ID).boundingBox();
  expect(targetBox).not.toBeNull();

  const targetRegion = {
    x: Math.floor(targetBox!.x),
    y: Math.floor(targetBox!.y),
    width: Math.ceil(targetBox!.width),
    height: Math.ceil(targetBox!.height),
  };

  await vision.clickByImage(page, asset('add-btn.png'), {
    region: targetRegion,
    confidence: 0.24,
    debugDir: '/home/pwuser/results/debug',
    debugLabel: 'catalog-target-card',
  });

  await expect(page.locator(TARGET_CARD_ID)).toHaveAttribute('data-added', 'true');
  await expect(page.locator(TARGET_STATUS_ID)).toHaveText('In cart');
  await expect(page.locator(DISTRACTOR_CARD_ID)).not.toHaveAttribute('data-added', 'true');
  await expect(page.locator('body')).toHaveAttribute('data-last-added', 'nimbus-lamp');
  await expect(page.locator('#cart-count')).toHaveText('1');
});
