/**
 * Teaser scene 1: Passing login test with vision highlights.
 *
 * Vision-only login flow from tc_vision_example_login, plus a
 * highlightLocator() call on the result text to draw attention
 * to "Signed in as operator".
 */
import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { asset, LOGIN_URL, LOGIN_CARD } from './functions';

test('teaser pass — login flow via vision selectors', async ({ page }) => {
  await page.goto(LOGIN_URL);
  await page.evaluate(() => document.fonts.ready);

  await vision.typeByImage(page, asset('username-field.png'), 'operator', {
    region: LOGIN_CARD,
  });

  await vision.typeByImage(page, asset('password-field.png'), 's3cret!Pass', {
    region: LOGIN_CARD,
  });

  await vision.clickByImage(page, asset('signin-cta.png'), {
    region: LOGIN_CARD,
  });

  // Wait for the result to appear, then highlight it for the recording
  const result = page.locator('#result');
  await expect(result).toContainText('Signed in as');
  await vision.highlightLocator(result, {
    highlightMs: 1500,
    highlightColor: '#4caf50',
    highlightFillColor: 'rgba(76, 175, 80, 0.15)',
  });
});
