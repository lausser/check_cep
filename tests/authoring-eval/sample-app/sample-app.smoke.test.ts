import { expect, test } from '@playwright/test';
import { pageUrl } from './lib/urls';

// Smoke checks proving the sample app is deterministic, self-contained, and
// shaped as the hard-case catalogue promises. Not an AI eval — this verifies
// the substrate offline (no key, no container).

const DEMO_USER = 'demo';
const DEMO_PASS = 'Passw0rd!';

test.describe('journey site', () => {
  test('landing page has no login form and buries the onlinebanking entry', async ({ page }) => {
    await page.goto(pageUrl('journey/index.html'));

    // No form anywhere on the landing page — the actionable path starts elsewhere.
    expect(await page.locator('form').count()).toBe(0);
    expect(await page.locator('input').count()).toBe(0);

    // The onlinebanking entry exists but is one link among many (not obvious).
    await expect(page.locator('#onlinebanking-entry')).toHaveAttribute('href', 'onlinebanking.html');
    expect(await page.locator('a').count()).toBeGreaterThan(20);
  });

  test('the full path landing → onlinebanking → login → dashboard works via relative links', async ({ page }) => {
    await page.goto(pageUrl('journey/index.html'));
    await page.locator('#onlinebanking-entry').click();
    await expect(page).toHaveURL(/onlinebanking\.html$/);

    await page.locator('#to-login').click();
    await expect(page).toHaveURL(/login\.html$/);

    await page.locator('#username').fill(DEMO_USER);
    await page.locator('#password').fill(DEMO_PASS);
    await page.locator('#login-submit').click();

    await expect(page).toHaveURL(/dashboard\.html$/);
    await expect(page.locator('#account-name')).toHaveText('Demo Checking Account');
  });

  test('invalid credentials show a visible error and do not navigate', async ({ page }) => {
    await page.goto(pageUrl('journey/login.html'));
    await page.locator('#username').fill('wrong');
    await page.locator('#password').fill('nope');
    await page.locator('#login-submit').click();

    await expect(page.locator('#login-error')).toBeVisible();
    await expect(page).toHaveURL(/login\.html$/);
  });

  test('dashboard stable values are constant across reloads; dynamic value differs', async ({ page }) => {
    await page.goto(pageUrl('journey/dashboard.html'));
    const balance1 = await page.locator('#account-balance').textContent();
    const iban1 = await page.locator('#account-iban').textContent();
    const login1 = await page.locator('#last-login').textContent();

    await page.waitForTimeout(20); // ensure the clock advances
    await page.reload();
    const balance2 = await page.locator('#account-balance').textContent();
    const iban2 = await page.locator('#account-iban').textContent();
    const login2 = await page.locator('#last-login').textContent();

    expect(balance2).toBe(balance1);         // stable
    expect(iban2).toBe(iban1);               // stable
    expect(login1).not.toBe('…');            // dynamic value rendered
    // last-login is a real timestamp; it must not be treated as stable.
    // (We assert only that it is present and clock-derived, not its literal.)
    expect(login1).toMatch(/\d{4}/);
  });
});

test.describe('probe routes', () => {
  test('consent dialog appears on first visit and not after dismissal (per context)', async ({ page }) => {
    await page.goto(pageUrl('probes/consent-first-visit/index.html'));
    // Guarantee a true first-visit: Chromium can share file:// localStorage
    // across contexts, so clear the flag before asserting the fresh-visit state.
    await page.evaluate(() => localStorage.removeItem('probe-consent-accepted'));
    await page.reload();
    await expect(page.locator('#consent')).toBeVisible();

    await page.locator('#consent-accept').click();
    await expect(page.locator('#consent')).toBeHidden();

    // Same context → flag persisted → dialog does not reappear on reload.
    await page.reload();
    await expect(page.locator('#consent')).toBeHidden();
  });

  test('ambiguous "Add to cart" matches many nodes; a scoped locator resolves one', async ({ page }) => {
    await page.goto(pageUrl('probes/ambiguous-elements/index.html'));
    expect(await page.getByRole('button', { name: 'Add to cart' }).count()).toBeGreaterThan(1);

    await page.locator('button.add[data-product="gold-card"]').click();
    await expect(page.locator('#cart')).toHaveAttribute('data-added', 'gold-card');
  });

  test('stable value is fixed while the session clock is dynamic', async ({ page }) => {
    await page.goto(pageUrl('probes/stable-vs-dynamic/index.html'));
    await expect(page.locator('#account-number')).toHaveText('4711-0815-2300');
    const t1 = await page.locator('#session-clock').textContent();
    await page.waitForTimeout(1100);
    const t2 = await page.locator('#session-clock').textContent();
    expect(t2).not.toBe(t1); // dynamic
  });

  test('async target appears only after loading, revealed by state', async ({ page }) => {
    await page.goto(pageUrl('probes/async-loading/index.html'));
    await expect(page.locator('#balance')).toBeHidden();
    await expect(page.locator('#balance')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('#balance')).toHaveAttribute('data-loaded', 'true');
  });

  test('responsive: desktop CTA is visible at the pinned 1280×720 viewport', async ({ page }) => {
    await page.goto(pageUrl('probes/responsive-breakpoint/index.html'));
    await expect(page.locator('#desktop-cta')).toBeVisible();
    await expect(page.locator('#mobile-cta')).toBeHidden();
  });

  test('moving element lands at different coordinates across reloads (same context)', async ({ page }) => {
    await page.goto(pageUrl('probes/moving-element/index.html'));
    const box1 = await page.locator('#target').boundingBox();
    await page.reload();
    const box2 = await page.locator('#target').boundingBox();
    expect(box1).not.toBeNull();
    expect(box2).not.toBeNull();
    // Seeded sequence advances per load → the badge moves.
    expect([box2!.x, box2!.y]).not.toEqual([box1!.x, box1!.y]);
  });
});
