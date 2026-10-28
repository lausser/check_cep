import { test, expect } from '@playwright/test';

test('page loads and links to IANA example-domain documentation', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(
    page.locator('a[href="https://iana.org/help/example-domains"]'),
  ).toHaveText('Learn more');
});
