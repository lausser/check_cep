import { expect, test } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { PAGE_URL, asset } from './functions';

// Ideal test for a control with no stable DOM handle (icon-only canvas, no
// id/role, randomised wrapper class): the sanctioned approach is an image
// template match, not a brittle selector.
test('activate the icon-only canvas control via image match', async ({ page }) => {
  await page.goto(PAGE_URL);

  await vision.clickByImage(page, asset('play-icon.png'));

  await expect(page.locator('#status')).toHaveAttribute('data-activated', 'true');
});
