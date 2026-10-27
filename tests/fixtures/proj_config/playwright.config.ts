import { defineConfig } from '@playwright/test';

// Standard Playwright project layout (spec 023 US3): the root config is
// applied as-is in project-root mode. Tests never navigate; they assert the
// baseURL to prove this config is the active one.
export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: {
    baseURL: 'http://cep.invalid/',
    headless: true,
    viewport: { width: 1280, height: 720 },
  },
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'main',
      dependencies: ['setup'],
      use: { browserName: 'chromium', storageState: 'playwright/.auth/user.json' },
    },
  ],
});
