/**
 * tc_vision_example_login — Realistic login flow on a visually busy page.
 *
 * Demonstrates a full login workflow on a page with a navigation bar,
 * gradient hero banner, feature cards sidebar, social login buttons
 * ("Sign in with Google", "Sign in with GitHub"), and the primary CTA.
 *
 * Two tests show different approaches:
 *   1. Vision-only — pure image matching with persistent templates
 *   2. Hybrid — vision-first with DOM fallback (production recommended)
 *
 * The CTA template (solid blue, full-width) is visually distinct from the
 * social login buttons, so vision matching picks the correct target without
 * ambiguity.  The username/password field templates include labels for
 * disambiguation.
 *
 * Render baseline: 1280x720 viewport, deviceScaleFactor: 1, Arial font.
 */
import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { asset, LOGIN_URL, LOGIN_CARD, assertLoginSubmitted } from './functions';

// ---------------------------------------------------------------------------
// Strategy 1: Vision-only
// ---------------------------------------------------------------------------
test('login flow via vision selectors', async ({ page }) => {
  await page.goto(LOGIN_URL);
  await page.evaluate(() => document.fonts.ready);

  // Type username — template includes the "Username" label for disambiguation.
  // Center-click lands on the input (label is top ~20px of the 61px-tall row).
  // debugDir writes diagnostic artifacts for post-mortem inspection.
  await vision.typeByImage(page, asset('username-field.png'), 'operator', {
    region: LOGIN_CARD,
    debugDir: '/home/pwuser/results/debug',
    debugLabel: 'username',
  });

  // Type password — template includes the "Password" label.
  await vision.typeByImage(page, asset('password-field.png'), 's3cret!Pass', {
    region: LOGIN_CARD,
  });

  // Click the primary Sign In CTA — visually distinct from social buttons.
  await vision.clickByImage(page, asset('signin-cta.png'), {
    region: LOGIN_CARD,
  });

  await expect(page.locator('#password')).toHaveValue('s3cret!Pass');
  await assertLoginSubmitted(page, 'operator');
});

// ---------------------------------------------------------------------------
// Strategy 2: Hybrid (vision-first with DOM fallback)
// ---------------------------------------------------------------------------
test('login flow via hybrid selectors', async ({ page }) => {
  await page.goto(LOGIN_URL);
  await page.evaluate(() => document.fonts.ready);

  // typeByImageOr: vision attempt first, CSS selector fallback.
  await vision.typeByImageOr(
    page,
    asset('username-field.png'),
    'operator',
    ['#username', 'input[name="username"]'],
    { region: LOGIN_CARD },
  );
  await vision.typeByImageOr(
    page,
    asset('password-field.png'),
    's3cret!Pass',
    ['#password', 'input[name="password"]'],
    { region: LOGIN_CARD },
  );

  // clickByImageOr: vision attempt first, Playwright locator fallback.
  await vision.clickByImageOr(
    page,
    asset('signin-cta.png'),
    [page.locator('#signin-btn')],
    { region: LOGIN_CARD },
  );

  await expect(page.locator('#password')).toHaveValue('s3cret!Pass');
  await assertLoginSubmitted(page, 'operator');
});
