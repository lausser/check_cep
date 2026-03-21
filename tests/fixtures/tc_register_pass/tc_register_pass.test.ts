import { test, expect, type Page } from '@playwright/test';

const username = 'user' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
const password = 'Test@1234';

async function expectRegistrationRejected(page: Page) {
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.locator('#username')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('Successfully registered');
}

test('successful registration, login and logout', async ({ page }) => {
  await page.goto('https://practice.expandtesting.com/register');
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.locator('#confirmPassword').fill(password);
  await page.locator('button[type="submit"]').click();
  // Registration redirects to /login with a success flash
  await expect(page.locator('.flash, .alert')).toContainText('Successfully registered');
  // Login form is now on screen (/login)
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(password);
  await page.locator('#submit-login').click();
  await expect(page.locator('#flash')).toContainText('You logged into a secure area!');
  // Logout via DOM locator
  await page.locator('a[href="/logout"]').click();
  await expect(page.locator('#flash')).toContainText('You logged out of the secure area!');
});

test('missing username shows error', async ({ page }) => {
  await page.goto('https://practice.expandtesting.com/register');
  await page.locator('#password').fill(password);
  await page.locator('#confirmPassword').fill(password);
  await page.locator('button[type="submit"]').click();
  await expectRegistrationRejected(page);
});

test('missing password shows error', async ({ page }) => {
  await page.goto('https://practice.expandtesting.com/register');
  await page.locator('#username').fill(username + 'np');
  await page.locator('#confirmPassword').fill(password);
  await page.locator('button[type="submit"]').click();
  await expectRegistrationRejected(page);
});

test('mismatched passwords shows error', async ({ page }) => {
  await page.goto('https://practice.expandtesting.com/register');
  await page.locator('#username').fill(username + 'mm');
  await page.locator('#password').fill(password);
  await page.locator('#confirmPassword').fill('different');
  await page.locator('button[type="submit"]').click();
  await expectRegistrationRejected(page);
});
