import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import { greet } from './functions/shared';

test('uses the shared layer', async ({ page }) => {
  await page.setContent(`<p>${greet()}</p>`);
  await expect(page.locator('p')).toHaveText('hi');
  // The merged tree is writable; the source layers are not touched.
  fs.writeFileSync('written-by-test.txt', 'x');
});
