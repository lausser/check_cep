import { expect, test } from '@playwright/test';
import { PAGE_URL } from './functions';

// Ideal test for async-loaded content: wait on the target's STATE, never a
// fixed sleep. The page's reveal delay is randomised, so a sleep would flake.
test('read the balance once it has asynchronously loaded', async ({ page }) => {
  await page.goto(PAGE_URL);

  // Wait on state: Playwright web-first assertions retry until the element is
  // visible / loaded — no arbitrary timeout guessing.
  const balance = page.locator('#balance');
  await expect(balance).toBeVisible();
  await expect(balance).toHaveAttribute('data-loaded', 'true');

  const value = ((await balance.textContent()) ?? '').replace(/[^\d.]/g, '');
  expect(Number(value)).toBeGreaterThan(0);
  console.log(`NagiosPerfData: 'AvailableBalance'=${value}`);
});
