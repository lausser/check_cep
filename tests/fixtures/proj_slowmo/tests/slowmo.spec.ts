import { test, expect } from '@playwright/test';

// FR-045 probe: CEP_SLOW_MO must reach launchOptions and really slow actions.
// The expected value arrives as --environ CEP_SLOW_MO_EXPECT=slowmo-<ms>.
test('slowMo takes effect', async ({ page }) => {
  const expected = Number(process.env.CEP_SLOW_MO_EXPECT!.replace(/^slowmo-/, ''));
  expect(test.info().project.use.launchOptions?.slowMo ?? 0).toBe(expected);
  await page.setContent('<button>b</button>');
  const start = Date.now();
  for (let i = 0; i < 10; i++) await page.click('button');
  expect(Date.now() - start).toBeGreaterThanOrEqual(10 * expected);
});
