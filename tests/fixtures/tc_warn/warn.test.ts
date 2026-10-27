import { test, expect } from '@playwright/test';

// spec 023 FR-053: a passing test that writes to stderr signals WARNING.
test('passes but complains', async ({ page }) => {
  await page.setContent('<p>ok</p>');
  await expect(page.locator('p')).toHaveText('ok');
  console.error('slow backend');
});
