import { test, expect } from '@playwright/test';
import { shopTitle } from '../../../functions';
import { shopName } from '../../../variables';

test('nested layout with shared helpers', async ({ page }) => {
  await page.setContent(`<h1>${shopTitle(shopName)}</h1>`);
  await expect(page.locator('h1')).toHaveText('Shop: Demo');
  test.info().annotations.push({ type: 'perfdata_items', description: '3' });
});
