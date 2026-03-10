/**
 * Shared helpers for tc_vision_example_login.
 *
 * Demonstrates the functions/ convention: reusable utilities that are
 * imported by test files but ignored by run.py's test discovery.
 */
import * as path from 'node:path';
import { expect } from '@playwright/test';

/** Resolve a template image from the committed assets/ directory. */
export const asset = (name: string) => path.resolve(`assets/${name}`);

/** URL for the local login page. */
export const LOGIN_URL = 'file://' + path.resolve('pages/login.html');

/**
 * Region covering the login card area.
 *
 * Derived from .login-card bounding box at 1280x720:
 *   { x: 640, y: 204, width: 380, height: 524 }
 */
export const LOGIN_CARD = { x: 630, y: 195, width: 400, height: 545 };

/** Assert that a login was submitted with the expected credentials. */
export async function assertLoginSubmitted(page: any, username: string) {
  await expect(page.locator('#username')).toHaveValue(username);
  await expect(page.locator('body')).toHaveAttribute('data-submitted', 'true');
  const result = await page.locator('#result').textContent();
  expect(result).toContain(username);
}
