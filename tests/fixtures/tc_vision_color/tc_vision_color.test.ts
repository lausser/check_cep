import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';

/**
 * tc_vision_color — Color distinction test.
 *
 * Two same-text "Proceed" buttons with similar grayscale luminance
 * but different colors (blue vs red). The color verification stage
 * should distinguish them and click the correct one.
 *
 * Validates: FR-013, SC-004
 */

const COLOR_BUTTONS_HTML = `
  <html><body style="margin:0; display:flex; justify-content:center; align-items:center; height:100vh; background:#f0f0f0; font-family:Arial,sans-serif;">
    <div style="display:flex; gap:120px;">
      <button id="btn-blue" onclick="window.__lastClicked='blue'"
        style="padding:14px 32px; background:rgb(0,82,200); color:white;
               border:none; border-radius:8px; font-size:18px; cursor:pointer;">
        Proceed
      </button>
      <button id="btn-red" onclick="window.__lastClicked='red'"
        style="padding:14px 32px; background:rgb(200,0,0); color:white;
               border:none; border-radius:8px; font-size:18px; cursor:pointer;">
        Proceed
      </button>
    </div>
  </body></html>
`;

test('clickByImage distinguishes red button from blue button by color', async ({ page }, testInfo) => {
  await page.setContent(COLOR_BUTTONS_HTML);
  await page.evaluate(() => document.fonts.ready);

  // Capture template from the red button
  const redTemplate = testInfo.outputPath('red-btn-template.png');
  await page.locator('#btn-red').screenshot({ path: redTemplate, animations: 'disabled' });

  // Search with fullPage so both buttons are in scope — color should distinguish
  const result = await vision.clickByImage(page, redTemplate, { fullPage: true });
  expect(result.found).toBe(true);

  // Assert the red button was clicked, not the blue one
  const clicked = await page.evaluate(() => (window as any).__lastClicked);
  expect(clicked).toBe('red');
});

test('clickByImage distinguishes blue button from red button by color', async ({ page }, testInfo) => {
  await page.setContent(COLOR_BUTTONS_HTML);
  await page.evaluate(() => document.fonts.ready);

  // Capture template from the blue button
  const blueTemplate = testInfo.outputPath('blue-btn-template.png');
  await page.locator('#btn-blue').screenshot({ path: blueTemplate, animations: 'disabled' });

  // Search with fullPage so both buttons are in scope
  const result = await vision.clickByImage(page, blueTemplate, { fullPage: true });
  expect(result.found).toBe(true);

  // Assert the blue button was clicked
  const clicked = await page.evaluate(() => (window as any).__lastClicked);
  expect(clicked).toBe('blue');
});
