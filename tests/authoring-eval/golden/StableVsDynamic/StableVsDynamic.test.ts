import { expect, test } from '@playwright/test';
import { PAGE_URL } from './functions';

// Ideal test for value-capture discipline: assert the stable value literally,
// capture the balance as perfdata, and NEVER assert the dynamic session clock.
test('assert stable identity, capture balance, leave the clock dynamic', async ({ page }) => {
  await page.goto(PAGE_URL);

  // Stable — safe to assert literally.
  await expect(page.locator('#account-number')).toHaveText('4711-0815-2300');

  // Capture the balance as perfdata (the requested value).
  const balanceText = (await page.locator('#balance').textContent()) ?? '';
  const balance = balanceText.replace(/[^\d.]/g, '');
  expect(Number(balance)).toBeGreaterThan(0);
  console.log(`NagiosPerfData: 'AvailableBalance'=${balance}`);

  // Dynamic — present, but must not be asserted for a specific value.
  await expect(page.locator('#session-clock')).not.toHaveText('…');
});
