import { expect, test } from '@playwright/test';

// Ideal test for iframe-embedded content: the target lives inside a same-origin
// frame, so the test must enter the frame (frameLocator) to actuate and read it.
// Targeting the top document would never find the button.
test('confirm the payment inside the iframe widget', async ({ page }) => {
  await page.goto('/index.html');

  const widget = page.frameLocator('#widget');
  await widget.locator('#frame-action').click();

  await expect(widget.locator('#frame-result')).toHaveAttribute('data-confirmed', 'true');
  await expect(widget.locator('#frame-result')).toContainText('€25.00');
});
