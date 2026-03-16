/**
 * Teaser scene 3: Failing login test — trailing space in username.
 *
 * Same vision-only login flow, but enters "operator " (trailing space).
 * The web app rejects the login and shows "Invalid credentials" in red
 * with light-red input backgrounds. After a 2-second pause (so the
 * viewer can absorb the failure), the test asserts "Signed in as"
 * which fails because the page shows "Invalid credentials".
 */
import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { asset, LOGIN_URL, LOGIN_CARD } from './functions';

test('teaser fail — login with trailing space', async ({ page }) => {
  await page.goto(LOGIN_URL);
  await page.evaluate(() => document.fonts.ready);

  await vision.typeByImage(page, asset('username-field.png'), 'operator ', {
    region: LOGIN_CARD,
  });

  await vision.typeByImage(page, asset('password-field.png'), 's3cret!Pass', {
    region: LOGIN_CARD,
  });

  await vision.clickByImage(page, asset('signin-cta.png'), {
    region: LOGIN_CARD,
  });

  // Wait for the result element to have content (success or error)
  const result = page.locator('#result');
  await expect(result).not.toBeEmpty();

  // Pause so the viewer can see the red "Invalid credentials" state
  await page.waitForTimeout(2000);

  // This assertion fails: page shows "Invalid credentials", not "Signed in as".
  // Short timeout so the test fails quickly instead of retrying for 60s.
  await expect(result).toContainText('Signed in as', { timeout: 1000 });
});
