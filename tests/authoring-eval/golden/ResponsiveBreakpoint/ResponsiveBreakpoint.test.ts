import { expect, test } from '@playwright/test';
import { PAGE_URL } from './functions';

// Ideal test for a responsive-breakpoint page: at the pinned 1280×720 viewport
// (config) the DESKTOP CTA is visible. This guards the 020 fix that aligned the
// exploration viewport with the run viewport — a mismatch would hide the target.
test('use the desktop transfer CTA at the pinned viewport', async ({ page }) => {
  await page.goto(PAGE_URL);

  await expect(page.locator('#desktop-cta')).toBeVisible();
  await expect(page.locator('#mobile-cta')).toBeHidden();

  await page.locator('#desktop-cta').click();
  await expect(page.locator('#result')).toHaveAttribute('data-done', 'true');
});
