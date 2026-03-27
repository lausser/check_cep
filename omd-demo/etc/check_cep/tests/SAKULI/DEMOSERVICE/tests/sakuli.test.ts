import { test, expect, Page } from '@playwright/test';
import { vision } from 'check-cep-vision'; // Needed for _highlight translation

// Set the render baseline as recommended by check-cep-vision for consistent results
test.use({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });

test('migration of Sakuli script to Playwright', async ({ page }) => {
  // Sakuli: await _navigateTo("https://sakuli.io");
  // Translation: Use page.goto()
  await page.goto('https://sakuli.io');

  // Sakuli: await _click(_link("Getting started"));
  // Translation: Use page.getByRole() for links
  await page.getByRole('link', { name: 'Getting started' }).click();

  // Sakuli: await _click(_link("Initialization"));
  // Translation: Use page.getByRole() for links
  await page.getByRole('link', { name: 'Initialization' }).click();

  // Sakuli: await _highlight(_code("npm init"));
  // Translation: Use vision.highlightLocator() for DOM elements.
  // Assuming _code() targets a code element containing the text.
  // Adding a default highlight duration.
  await vision.highlightLocator(page.locator('code', { hasText: 'npm init' }), { highlightMs: 700 });
});
