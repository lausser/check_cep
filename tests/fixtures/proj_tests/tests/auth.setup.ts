import { test as setup } from '@playwright/test';

// Setup project: writes the storage state the main project depends on.
// The merged test tree is writable, so this works in a layered check.
setup('authenticate', async ({ page }) => {
  await page.setContent('<p>x</p>');
  await page.context().storageState({ path: 'playwright/.auth/user.json' });
});
