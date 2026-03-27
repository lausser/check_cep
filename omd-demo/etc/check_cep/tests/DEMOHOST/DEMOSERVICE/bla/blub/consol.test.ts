import { test, expect } from '@playwright/test';

test('should find Coshsh on consol.de', async ({ page }) => {
  // Navigate to https://www.consol.de
  await page.goto('https://www.consol.de');

  // Click on 'Product Solutions'
  await page.getByRole('button', { name: 'Product Solutions' }).click();

  // Click on 'Open Source Monitoring'
  await page.getByRole('link', { name: 'Open Source Monitoring Wir' }).click();

  // Assert that 'Coshsh' exists on the page
  const coshshExists = await page.evaluate(() => document.body.innerText.includes('Coshsh'));
  expect(coshshExists).toBe(true);
});

