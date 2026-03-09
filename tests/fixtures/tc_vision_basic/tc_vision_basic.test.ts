import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';

/**
 * tc_vision_basic — Vision helper smoke tests.
 *
 * All tests use inline HTML via page.setContent() for determinism.
 * Templates are captured dynamically via testInfo.outputPath().
 * Region presets assume 1280x720 viewport with deviceScaleFactor: 1
 * (enforced by the shared playwright.config.ts).
 */

test('clickByImage: find and click a button by template image', async ({ page }, testInfo) => {
  // Set deterministic page content with a styled button
  await page.setContent(`
    <html><body style="margin:0; display:flex; justify-content:center; align-items:center; height:100vh; background:#f0f0f0;">
      <button id="btn" onclick="window.__clicked=true"
        style="padding:14px 32px; background:#2563eb; color:white;
               border:none; border-radius:8px; font-size:18px; font-family:Arial,sans-serif; cursor:pointer;">
        Submit
      </button>
    </body></html>
  `);
  await page.evaluate(() => document.fonts.ready);

  // Capture template from the button (DOM selector OK during capture)
  const templatePath = testInfo.outputPath('btn-template.png');
  await page.locator('#btn').screenshot({ path: templatePath, animations: 'disabled' });

  // Reload to break DOM state coupling
  await page.reload();
  await page.setContent(`
    <html><body style="margin:0; display:flex; justify-content:center; align-items:center; height:100vh; background:#f0f0f0;">
      <button id="btn" onclick="window.__clicked=true"
        style="padding:14px 32px; background:#2563eb; color:white;
               border:none; border-radius:8px; font-size:18px; font-family:Arial,sans-serif; cursor:pointer;">
        Submit
      </button>
    </body></html>
  `);
  await page.evaluate(() => document.fonts.ready);

  // Use vision to find and click — no DOM selector
  const result = await vision.clickByImage(page, templatePath, { region: 'main' });
  expect(result.found).toBe(true);
  expect(result.clickPoint).toBeDefined();

  // Assert click actually happened
  const clicked = await page.evaluate(() => (window as any).__clicked);
  expect(clicked).toBe(true);
});

test('typeByImage: find input and type text by template image', async ({ page }, testInfo) => {
  const inputHtml = `
    <html><body style="margin:0; display:flex; justify-content:center; align-items:center; height:100vh; background:#f0f0f0;">
      <div style="display:flex; align-items:center; gap:12px;">
        <label style="font-size:16px; font-family:Arial,sans-serif;">Name:</label>
        <input id="name-input" type="text"
          style="padding:10px 16px; font-size:16px; font-family:Arial,sans-serif;
                 border:2px solid #2563eb; border-radius:6px; width:200px;" />
      </div>
    </body></html>
  `;

  await page.setContent(inputHtml);
  await page.evaluate(() => document.fonts.ready);

  // Capture template of the input area
  const templatePath = testInfo.outputPath('input-template.png');
  await page.locator('#name-input').screenshot({ path: templatePath, animations: 'disabled' });

  // Reload and re-set content
  await page.reload();
  await page.setContent(inputHtml);
  await page.evaluate(() => document.fonts.ready);

  // Use vision to click the input and type
  await vision.typeByImage(page, templatePath, 'Alice', { region: 'main' });

  // Assert the input received the text
  const value = await page.locator('#name-input').inputValue();
  expect(value).toBe('Alice');
});

test('existsByImage: check presence with region presets', async ({ page }, testInfo) => {
  // Page with a logo-like element in the header area and a button in the main area
  await page.setContent(`
    <html><body style="margin:0; font-family:Arial,sans-serif;">
      <header style="height:80px; background:#1e293b; display:flex; align-items:center; padding:0 24px;">
        <span id="logo" style="color:white; font-size:24px; font-weight:bold; background:#3b82f6; padding:8px 20px; border-radius:6px;">
          CEP Monitor
        </span>
      </header>
      <main style="display:flex; justify-content:center; align-items:center; height:calc(100vh - 160px);">
        <button id="action-btn"
          style="padding:14px 32px; background:#16a34a; color:white;
                 border:none; border-radius:8px; font-size:18px; cursor:pointer;">
          Run Check
        </button>
      </main>
      <footer style="height:80px; background:#334155; display:flex; align-items:center; justify-content:center;">
        <span style="color:#94a3b8; font-size:14px;">&copy; 2026 CEP Project</span>
      </footer>
    </body></html>
  `);
  await page.evaluate(() => document.fonts.ready);

  // Capture templates
  const logoTemplate = testInfo.outputPath('logo-template.png');
  const buttonTemplate = testInfo.outputPath('button-template.png');
  await page.locator('#logo').screenshot({ path: logoTemplate, animations: 'disabled' });
  await page.locator('#action-btn').screenshot({ path: buttonTemplate, animations: 'disabled' });

  // Logo should exist in header, not in footer
  const logoInHeader = await vision.existsByImage(page, logoTemplate, { region: 'header' });
  expect(logoInHeader).toBe(true);

  const logoInFooter = await vision.existsByImage(page, logoTemplate, { region: 'footer' });
  expect(logoInFooter).toBe(false);

  // Button should exist in main area
  const buttonInMain = await vision.existsByImage(page, buttonTemplate, { region: 'main' });
  expect(buttonInMain).toBe(true);
});
