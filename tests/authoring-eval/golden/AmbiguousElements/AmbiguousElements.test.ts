import { expect, test } from '@playwright/test';
import { PAGE_URL } from './functions';

// Ideal test for ambiguous look-alike buttons: the generic name matches many
// nodes, so the intended one must be disambiguated to EXACTLY one (no
// strict-mode violation).
test('add exactly the Gold Credit Card despite look-alike buttons', async ({ page }) => {
  await page.goto(PAGE_URL);

  // The generic accessible name is intentionally ambiguous — prove it.
  expect(await page.getByRole('button', { name: 'Add to cart' }).count()).toBeGreaterThan(1);

  // Disambiguate to one node via the stable product scope.
  const goldAdd = page.locator('button.add[data-product="gold-card"]');
  await expect(goldAdd).toHaveCount(1);
  await goldAdd.click();

  await expect(page.locator('#cart')).toHaveAttribute('data-added', 'gold-card');
});
