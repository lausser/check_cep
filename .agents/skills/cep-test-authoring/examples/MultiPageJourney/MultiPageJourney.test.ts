import { expect, test } from '@playwright/test';
import { DEMO_PASS, DEMO_USER, LANDING_URL, toNumber } from './functions';

// Ideal deterministic test for the flagship multi-page distraction journey:
// landing → onlinebanking → login → dashboard. Steps are named after business
// actions so each becomes a per-step perfdata metric; the captured balance is
// emitted with the documented `NagiosPerfData:` stdout convention.

test('sign in through the multi-page journey and read the dashboard balance', async ({ page }) => {
  await test.step('open landing page', async () => {
    await page.goto(LANDING_URL);
    // The landing page deliberately has no login form.
    await expect(page.locator('form')).toHaveCount(0);
  });

  await test.step('enter online banking', async () => {
    // The entry is one link among many in the top utility bar — target it by its
    // stable id, not by position.
    await page.locator('#onlinebanking-entry').click();
    await expect(page).toHaveURL(/onlinebanking\.html$/);
  });

  await test.step('go to the login wall', async () => {
    // The non-obvious "Sign in to your account" promo link.
    await page.locator('#to-login').click();
    await expect(page).toHaveURL(/login\.html$/);
  });

  await test.step('sign in', async () => {
    await page.locator('#username').fill(DEMO_USER);
    await page.locator('#password').fill(DEMO_PASS);
    await page.locator('#login-submit').click();
    await expect(page).toHaveURL(/dashboard\.html$/);
  });

  await test.step('verify dashboard', async () => {
    // Stable signals — safe to assert literally.
    await expect(page.locator('#account-name')).toHaveText('Demo Checking Account');
    await expect(page.locator('#account-iban')).toHaveText('DE89 3704 0044 0532 0130 00');

    const balanceText = (await page.locator('#account-balance').textContent()) ?? '';
    const balance = toNumber(balanceText);
    expect(Number(balance)).toBeGreaterThan(0);

    // Capture the balance as perfdata (the requested "Value to Capture").
    console.log(`NagiosPerfData: 'AvailableBalance'=${balance}`);

    // The "Last login" is dynamic — assert only that it is present, never its
    // literal value.
    await expect(page.locator('#last-login')).not.toHaveText('…');
  });
});
