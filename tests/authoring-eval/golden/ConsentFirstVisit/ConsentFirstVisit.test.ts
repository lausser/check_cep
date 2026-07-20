import { expect, test } from '@playwright/test';
import { PAGE_URL } from './functions';

// Ideal test for a sometimes-present consent dialog: dismiss it IF shown, then
// proceed. Must pass whether or not the dialog appears (robust handling), not
// assume it is always there.
test('open the account report after handling optional consent', async ({ page }) => {
  await page.goto(PAGE_URL);

  const consent = page.locator('#consent');
  // Robust: handle "appears sometimes" — dismiss only if visible.
  if (await consent.isVisible()) {
    await page.locator('#consent-accept').click();
    await expect(consent).toBeHidden();
  }

  await page.locator('#open-report').click();
  await expect(page.locator('#report')).toHaveAttribute('data-opened', 'true');
});
