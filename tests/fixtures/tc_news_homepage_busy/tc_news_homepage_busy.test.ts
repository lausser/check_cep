import { expect, test } from '@playwright/test';
import { vision } from 'check-cep-vision';
import {
  asset,
  DISTRACTOR_STORY_ID,
  NEWS_URL,
  TARGET_STORY_ID,
} from './functions';

test('broad story-button search is unsafe on a busy homepage', async ({ page }) => {
  await page.goto(NEWS_URL);
  await page.evaluate(() => document.fonts.ready);

  expect(await page.locator('.story-btn').count()).toBeGreaterThan(3);

  const result = await vision.locateByImage(page, asset('story-btn.png'), {
    region: 'main',
  });

  expect(result.found).toBe(true);
  expect(result.reason).toBe('found');
});

test('cookie dismissal is required before guided story click', async ({ page }) => {
  await page.goto(NEWS_URL);
  await page.evaluate(() => document.fonts.ready);

  await expect(page.locator('#cookie-banner')).toBeVisible();
  await page.locator('#open-target-story').click();
  await expect(page.locator('body')).toHaveAttribute('data-opened-story', 'none');

  await vision.clickByImage(page, asset('accept-btn.png'), {
    region: 'footer',
  });

  await expect(page.locator('#cookie-banner')).toBeHidden();
  await expect(page.locator('body')).toHaveAttribute('data-consent', 'accepted');
  await page.locator(TARGET_STORY_ID).scrollIntoViewIfNeeded();

  const targetBox = await page.locator(TARGET_STORY_ID).boundingBox();
  expect(targetBox).not.toBeNull();

  const targetRegion = {
    x: Math.floor(targetBox!.x),
    y: Math.floor(targetBox!.y),
    width: Math.ceil(targetBox!.width),
    height: Math.ceil(targetBox!.height),
  };

  await vision.clickByImage(page, asset('story-btn.png'), {
    region: targetRegion,
    confidence: 0.48,
    debugDir: '/home/pwuser/results/debug',
    debugLabel: 'news-guided-story',
  });

  await expect(page.locator('body')).toHaveAttribute('data-opened-story', 'harbor-dossier');
  await expect(page.locator('#story-result')).toContainText('Harbor Dossier');
  await expect(page.locator(TARGET_STORY_ID)).toHaveAttribute('data-opened', 'true');
  await expect(page.locator(DISTRACTOR_STORY_ID)).not.toHaveAttribute('data-opened', 'true');
});
