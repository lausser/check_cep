import { test, expect } from '@playwright/test';

test('fill and display inputs', async ({ page }) => {
  await page.goto('https://practice.expandtesting.com/inputs');
  await page.locator('#input-number').fill('42');
  await page.locator('#input-text').fill('hello world');
  await page.locator('#input-password').fill('s3cr3t');
  await page.locator('#input-date').fill('2024-06-15');
  await page.locator('#btn-display-inputs').click();
  await expect(page.locator('[data-testid="number-output"], #output-number, .output-number').first()).toContainText('42');
  await expect(page.locator('[data-testid="text-output"], #output-text, .output-text').first()).toContainText('hello world');
});

test('clear inputs', async ({ page }) => {
  await page.goto('https://practice.expandtesting.com/inputs');
  await page.locator('#input-number').fill('99');
  await page.locator('#input-text').fill('to be cleared');
  await page.locator('#btn-display-inputs').click();
  await page.locator('#btn-clear-inputs').click();
  await expect(page.locator('#input-number')).toHaveValue('');
  await expect(page.locator('#input-text')).toHaveValue('');
});
