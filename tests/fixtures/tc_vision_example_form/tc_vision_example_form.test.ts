/**
 * tc_vision_example_form — Side-by-side comparison of three selector strategies.
 *
 * Demonstrates filling the same multi-field contact form using:
 *   1. Vision-only selectors (typeByImage / clickByImage with persistent templates)
 *   2. DOM-only selectors (standard Playwright locators)
 *   3. Hybrid selectors (typeByImageOr / clickByImageOr — vision first, DOM fallback)
 *
 * All three tests verify the same behavioural outcome: fields are filled
 * correctly and the form is submitted.
 *
 * Template images live in assets/ and capture the full field row (label + input)
 * so the label text disambiguates identical-looking input fields.  A clickOffset
 * is used to shift the click from the row center into the input area.
 *
 * Render baseline: 1280x720 viewport, deviceScaleFactor: 1, Arial font.
 */
import { test } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { FORM_DATA } from './variables';
import { asset, FORM_URL, INPUT_OFFSET, assertFormFilled } from './functions';

// ---------------------------------------------------------------------------
// Strategy 1: Vision-only
// ---------------------------------------------------------------------------
test('form filling via vision selectors', async ({ page }) => {
  await page.goto(FORM_URL);
  await page.evaluate(() => document.fonts.ready);

  await vision.typeByImage(page, asset('name-row.png'), FORM_DATA.name, {
    region: 'main',
    clickOffset: INPUT_OFFSET,
  });
  await vision.typeByImage(page, asset('prename-row.png'), FORM_DATA.prename, {
    region: 'main',
    clickOffset: INPUT_OFFSET,
  });
  await vision.typeByImage(page, asset('city-row.png'), FORM_DATA.city, {
    region: 'main',
    clickOffset: INPUT_OFFSET,
  });
  await vision.clickByImage(page, asset('submit-btn.png'), {
    region: 'main',
  });

  await assertFormFilled(page);
});

// ---------------------------------------------------------------------------
// Strategy 2: DOM-only
// ---------------------------------------------------------------------------
test('form filling via DOM selectors', async ({ page }) => {
  await page.goto(FORM_URL);
  await page.evaluate(() => document.fonts.ready);

  await page.locator('#name-input').fill(FORM_DATA.name);
  await page.locator('#prename-input').fill(FORM_DATA.prename);
  await page.locator('#city-input').fill(FORM_DATA.city);
  await page.locator('#submit-btn').click();

  await assertFormFilled(page);
});

// ---------------------------------------------------------------------------
// Strategy 3: Hybrid (vision-first with DOM fallback)
// ---------------------------------------------------------------------------
test('form filling via hybrid selectors', async ({ page }) => {
  await page.goto(FORM_URL);
  await page.evaluate(() => document.fonts.ready);

  // typeByImageOr: vision attempt first, falls back to fillFirstVisible
  // with CSS selector strings (not Playwright locators).
  await vision.typeByImageOr(
    page,
    asset('name-row.png'),
    FORM_DATA.name,
    ['#name-input', 'input[name="name"]'],
    { region: 'main', clickOffset: INPUT_OFFSET },
  );
  await vision.typeByImageOr(
    page,
    asset('prename-row.png'),
    FORM_DATA.prename,
    ['#prename-input', 'input[name="prename"]'],
    { region: 'main', clickOffset: INPUT_OFFSET },
  );
  await vision.typeByImageOr(
    page,
    asset('city-row.png'),
    FORM_DATA.city,
    ['#city-input', 'input[name="city"]'],
    { region: 'main', clickOffset: INPUT_OFFSET },
  );

  // clickByImageOr: vision attempt first, falls back to clickFirstVisible
  // with Playwright locators (not CSS strings).
  await vision.clickByImageOr(
    page,
    asset('submit-btn.png'),
    [page.locator('#submit-btn')],
    { region: 'main' },
  );

  await assertFormFilled(page);
});
