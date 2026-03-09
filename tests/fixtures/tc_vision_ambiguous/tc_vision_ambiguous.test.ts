import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';

/**
 * tc_vision_ambiguous — Ambiguity rejection and region-based resolution.
 *
 * Two identical red "Delete" buttons in a two-column layout.
 * Without a region constraint, matching should report 'ambiguous'.
 * With region:'right', only the right button should be clicked.
 *
 * Validates: FR-016, SC-003
 */

const TWO_BUTTON_HTML = `
  <html><body style="margin:0; display:flex; justify-content:center; align-items:center; height:100vh; background:#f0f0f0; font-family:Arial,sans-serif;">
    <div style="display:flex; gap:200px;">
      <div style="text-align:center;">
        <p style="margin-bottom:12px; color:#666;">Left Column</p>
        <button id="btn-left" onclick="window.__lastClicked='left'"
          style="padding:14px 32px; background:#dc2626; color:white;
                 border:none; border-radius:8px; font-size:18px; cursor:pointer;">
          Delete
        </button>
      </div>
      <div style="text-align:center;">
        <p style="margin-bottom:12px; color:#666;">Right Column</p>
        <button id="btn-right" onclick="window.__lastClicked='right'"
          style="padding:14px 32px; background:#dc2626; color:white;
                 border:none; border-radius:8px; font-size:18px; cursor:pointer;">
          Delete
        </button>
      </div>
    </div>
  </body></html>
`;

test('locateByImage reports ambiguous when two identical buttons exist', async ({ page }, testInfo) => {
  await page.setContent(TWO_BUTTON_HTML);
  await page.evaluate(() => document.fonts.ready);

  // Capture template from the left button
  const templatePath = testInfo.outputPath('delete-btn-template.png');
  await page.locator('#btn-left').screenshot({ path: templatePath, animations: 'disabled' });

  // locateByImage without region constraint — should detect ambiguity
  // Use fullPage to search the entire viewport (no default inset clipping)
  const result = await vision.locateByImage(page, templatePath, { fullPage: true });
  expect(result.found).toBe(false);
  expect(result.reason).toBe('ambiguous');
});

test('clickByImage with region:right resolves ambiguity', async ({ page }, testInfo) => {
  await page.setContent(TWO_BUTTON_HTML);
  await page.evaluate(() => document.fonts.ready);

  // Capture template from the left button (identical to right)
  const templatePath = testInfo.outputPath('delete-btn-template.png');
  await page.locator('#btn-left').screenshot({ path: templatePath, animations: 'disabled' });

  // Click with region:'right' to resolve ambiguity — only right button is in search area
  const result = await vision.clickByImage(page, templatePath, { region: 'right' });
  expect(result.found).toBe(true);
  expect(result.regionWasClipped).toBe(false);

  // Assert the right button was clicked
  const clicked = await page.evaluate(() => (window as any).__lastClicked);
  expect(clicked).toBe('right');
});
