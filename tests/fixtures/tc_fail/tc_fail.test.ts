import { test, expect } from '@playwright/test';

const username = 'fail' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
const password = 'Test@1234';

test('expect wrong success message (deliberate failure)', async ({ page }) => {
  await page.goto('https://practice.expandtesting.com/register');
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.locator('#confirmPassword').fill(password);
  await page.locator('button[type="submit"]').click();
  // Intentionally wrong text — assertion will fail (deliberate)
  await expect(page.locator('body')).toContainText('Welcome back!');
});
