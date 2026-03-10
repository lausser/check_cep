/**
 * Shared helpers for tc_vision_example_form.
 *
 * Demonstrates the functions/ convention: reusable utilities that are
 * imported by test files but ignored by run.py's test discovery.
 */
import * as path from 'node:path';
import { expect } from '@playwright/test';
import { FORM_DATA } from '../variables';

/** Resolve a template image from the committed assets/ directory. */
export const asset = (name: string) => path.resolve(`assets/${name}`);

/** URL for the local form page. */
export const FORM_URL = 'file://' + path.resolve('pages/form.html');

/**
 * Click offset to target the input zone within field-row templates.
 *
 * Field-row PNGs are 424×42 px.  The label occupies ~110 px on the left;
 * the input starts around x≈120.  Offset { x: 300, y: 21 } places the
 * click squarely inside the input, well clear of the label.
 */
export const INPUT_OFFSET = { x: 300, y: 21 };

/** Assert that all three fields contain the expected values and the form was submitted. */
export async function assertFormFilled(page: any) {
  await expect(page.locator('#name-input')).toHaveValue(FORM_DATA.name);
  await expect(page.locator('#prename-input')).toHaveValue(FORM_DATA.prename);
  await expect(page.locator('#city-input')).toHaveValue(FORM_DATA.city);
  await expect(page.locator('body')).toHaveAttribute('data-submitted', 'true');

  const result = await page.locator('#result').textContent();
  expect(result).toContain(FORM_DATA.name);
  expect(result).toContain(FORM_DATA.prename);
  expect(result).toContain(FORM_DATA.city);
}
