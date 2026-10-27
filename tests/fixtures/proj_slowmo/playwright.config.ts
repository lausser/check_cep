import { defineConfig } from '@playwright/test';

// Two projects with their own `use` blocks: the spectate wrapper must put
// slowMo into each of them (spec 023 FR-045).
export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  projects: [
    { name: 'a', use: { browserName: 'chromium', headless: true } },
    { name: 'b', use: { browserName: 'chromium', headless: true, viewport: { width: 800, height: 600 } } },
  ],
});
