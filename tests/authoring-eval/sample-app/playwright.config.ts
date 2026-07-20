import { defineConfig } from '@playwright/test';

// Smoke-test config for the sample app. All pages are served via file://
// (no webServer) at the pinned 1280×720 viewport. The iframe probe is the one
// HTTP-served exception and carries its own config under probes/iframe/.
export default defineConfig({
  testDir: '.',
  testMatch: '**/*.smoke.test.ts',
  timeout: 30000,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
