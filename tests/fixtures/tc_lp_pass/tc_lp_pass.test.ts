import { test, expect } from '@playwright/test';

test('page loads and contains expected text', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(page.locator('h1')).toContainText('Example Domain');
  await expect(page.locator('p').first()).toContainText('documentation examples');
});
