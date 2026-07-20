import { expect, test } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { PAGE_URL, asset } from './functions';

// Ideal test for a deterministic-but-moving target: the badge lands at a new
// (seeded) position every load, so absolute-coordinate / CSS-path clicks break.
// The image/best-effort fallback finds the badge wherever it is.
test('catch the moving badge via image match, wherever it lands', async ({ page }) => {
  await page.goto(PAGE_URL);

  await vision.clickByImage(page, asset('badge.png'));

  await expect(page.locator('#status')).toHaveAttribute('data-caught', 'true');
});
