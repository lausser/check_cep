import { test, expect } from '@playwright/test';

test('consol.de has Consulting & Solutions', async ({ page }) => {
  await page.goto('https://www.consol.de');
  await expect(page.locator('body')).toContainText('Consulting & Solutions');
});
