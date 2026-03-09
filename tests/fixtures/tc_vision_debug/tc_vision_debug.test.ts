import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';
import * as fs from 'fs';
import * as path from 'path';

/**
 * tc_vision_debug — Debug artifact generation on match failure.
 *
 * Captures a template from a styled button, then navigates to a blank page
 * where the target is absent. Calls locateByImage with debugDir set.
 * Asserts that debug artifacts ({label}-region.png, {label}-annotated.png,
 * {label}-meta.json) are written.
 *
 * Validates: FR-025, FR-026, SC-008
 */

test('locateByImage writes debug artifacts on failure', async ({ page }, testInfo) => {
  // Render a page with a styled button
  await page.setContent(`
    <html><body style="margin:0; display:flex; justify-content:center; align-items:center; height:100vh; background:#f0f0f0; font-family:Arial,sans-serif;">
      <button id="target-btn"
        style="padding:14px 32px; background:#7c3aed; color:white;
               border:none; border-radius:8px; font-size:18px; cursor:pointer;">
        Debug Me
      </button>
    </body></html>
  `);
  await page.evaluate(() => document.fonts.ready);

  // Capture template
  const templatePath = testInfo.outputPath('debug-btn-template.png');
  await page.locator('#target-btn').screenshot({ path: templatePath, animations: 'disabled' });

  // Navigate to blank page — target is now absent
  await page.setContent(`
    <html><body style="margin:0; height:100vh; background:#ffffff;">
      <p style="padding:40px; color:#999; font-family:Arial,sans-serif;">This page has no button.</p>
    </body></html>
  `);

  // Set up debug directory
  const debugDir = testInfo.outputPath('debug-artifacts');
  fs.mkdirSync(debugDir, { recursive: true });

  // locateByImage with debugDir — should fail (not-found) and write artifacts
  const result = await vision.locateByImage(page, templatePath, {
    region: 'main',
    debugDir: debugDir,
    debugLabel: 'btn-search',
  });

  expect(result.found).toBe(false);
  expect(result.reason).toBe('not-found');

  // Verify debug artifacts exist
  const regionPng = path.join(debugDir, 'btn-search-region.png');
  const annotatedPng = path.join(debugDir, 'btn-search-annotated.png');
  const metaJson = path.join(debugDir, 'btn-search-meta.json');

  expect(fs.existsSync(regionPng)).toBe(true);
  expect(fs.existsSync(annotatedPng)).toBe(true);
  expect(fs.existsSync(metaJson)).toBe(true);

  // Verify meta.json content is valid JSON with expected fields
  const meta = JSON.parse(fs.readFileSync(metaJson, 'utf-8'));
  expect(meta.reason).toBe('not-found');
  expect(meta).toHaveProperty('region');
});
