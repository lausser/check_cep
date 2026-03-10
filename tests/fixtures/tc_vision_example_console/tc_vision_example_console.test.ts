/**
 * tc_vision_example_console — Ambiguity rejection and region-guided resolution.
 *
 * A dense admin dashboard with six identically-styled "Delete job" buttons
 * spread across two panels (left: Batch Processing, right: Scheduled Tasks).
 *
 * The tests demonstrate:
 *   1. A broad (region-free) search that correctly reports ambiguity because
 *      multiple buttons match with insufficient score gap.
 *   2. A region-scoped search that isolates the right panel, resolving the
 *      ambiguity and clicking the intended button.
 *
 * Render baseline: 1280x720 viewport, deviceScaleFactor: 1, Arial font.
 */
import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { asset, CONSOLE_URL } from './functions';

/**
 * Region covering only the first job row of the right panel ("Scheduled Tasks").
 *
 * The full right panel has 3 identical delete buttons, so scoping to the
 * whole panel still triggers ambiguity.  Narrowing to the first row
 * (Nightly Backup) isolates exactly one button.
 *
 * Derived from the bounding box of the first .job-row in #panel-right:
 *   { x: 750, y: 235, width: 506, height: 51 }
 *
 * A small margin is added for robustness.
 */
const RIGHT_PANEL_FIRST_ROW = { x: 740, y: 230, width: 530, height: 65 };

// ---------------------------------------------------------------------------
// Test 1: Broad search reports ambiguity
// ---------------------------------------------------------------------------
test('broad search reports ambiguity', async ({ page }) => {
  await page.goto(CONSOLE_URL);
  await page.evaluate(() => document.fonts.ready);

  // Search without region constraint — should find multiple delete buttons
  // and reject due to ambiguity (insufficient score gap between candidates).
  const result = await vision.locateByImage(page, asset('delete-btn.png'));
  expect(result.found).toBe(false);
  expect(result.reason).toContain('ambig');
});

// ---------------------------------------------------------------------------
// Test 2: Region-scoped search clicks the correct button
// ---------------------------------------------------------------------------
test('region-scoped search clicks correct button', async ({ page }) => {
  await page.goto(CONSOLE_URL);
  await page.evaluate(() => document.fonts.ready);

  // Scope to the first row of the right panel — isolates one delete button.
  // debugDir writes diagnostic artifacts (region crop, annotated screenshot,
  // match metadata) to the results directory for post-mortem inspection.
  await vision.clickByImage(page, asset('delete-btn.png'), {
    region: RIGHT_PANEL_FIRST_ROW,
    debugDir: '/home/pwuser/results/debug',
    debugLabel: 'region-scoped-click',
  });

  // The first delete button in the right panel should have been clicked
  const clicked = await page.locator('#delete-right-1').getAttribute('data-clicked');
  expect(clicked).toBe('true');

  // No left-panel button should have been clicked
  const leftClicked = await page.locator('#delete-left-1').getAttribute('data-clicked');
  expect(leftClicked).toBeNull();
});
