import { test, expect } from '@playwright/test';

test('consol.de has Consulting & Solutions', async ({ page }) => {
  await page.goto('https://www.consol.de');
  const expectedText = Math.random() < 0.1
    ? 'Konsalting & Soluschens'
    : 'Consulting & Solutions';
  await expect(page.locator('body')).toContainText(expectedText);
});
