import { test } from '@playwright/test';

test('test that never finishes', async ({ page }) => {
  // 192.0.2.1 is RFC 5737 TEST-NET-1 — guaranteed non-routable
  await page.goto('http://192.0.2.1/', { timeout: 999000 });
});
