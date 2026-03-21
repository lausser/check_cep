import { expect, test } from '@playwright/test';
import { vision } from 'check-cep-vision';
import {
  asset,
  DISTRACTOR_TILE_ID,
  MARKETPLACE_URL,
  TARGET_STATUS_ID,
  TARGET_TILE_ID,
} from './functions';

test('preview crop is ambiguous across the twin dryer tiles', async ({ page }) => {
  await page.goto(MARKETPLACE_URL);
  await page.evaluate(() => document.fonts.ready);

  const result = await vision.locateByImage(page, asset('aurora-preview.png'), {
    fullPage: true,
    confidence: 0.55,
  });

  expect(result.found).toBe(false);
  expect(result.reason).toContain('ambig');
});

test('anchor badge isolates the target region, then preview click opens only the target tile', async ({ page }) => {
  await page.goto(MARKETPLACE_URL);
  await page.evaluate(() => document.fonts.ready);

  const anchor = await vision.locateByImage(page, asset('night-sale-badge.png'), {
    fullPage: true,
    confidence: 0.9,
    debugDir: '/home/pwuser/results/debug',
    debugLabel: 'anchor-badge-match',
  });

  expect(anchor.found).toBe(true);
  expect(anchor.reason).toBe('found');
  expect(anchor.bestCandidate).not.toBeNull();

  const candidate = anchor.bestCandidate!;
  await page.evaluate((scrollY) => window.scrollTo(0, Math.max(0, scrollY)), candidate.y - 40);
  await page.waitForTimeout(100);

  const viewportAnchorY = await page.evaluate((pageY) => pageY - window.scrollY, candidate.y);
  const stagedRegion = {
    x: Math.max(0, Math.floor(candidate.x - 20)),
    y: Math.max(0, Math.floor(viewportAnchorY - 10)),
    width: Math.ceil(candidate.width + 220),
    height: Math.ceil(candidate.height + 210),
  };

  await vision.clickByImage(page, asset('aurora-preview.png'), {
    region: stagedRegion,
    confidence: 0.83,
    clickOffset: { x: 48, y: 48 },
    debugDir: '/home/pwuser/results/debug',
    debugLabel: 'anchor-then-target-preview',
  });

  await expect(page.locator('body')).toHaveAttribute('data-opened-item', 'aurora-supersonic');
  await expect(page.locator(TARGET_TILE_ID)).toHaveAttribute('data-opened', 'true');
  await expect(page.locator(TARGET_STATUS_ID)).toHaveText('Opened');
  await expect(page.locator(DISTRACTOR_TILE_ID)).not.toHaveAttribute('data-opened', 'true');
  await expect(page.locator('#detail-panel')).toContainText('Aurora Supersonic Dryer');
});
