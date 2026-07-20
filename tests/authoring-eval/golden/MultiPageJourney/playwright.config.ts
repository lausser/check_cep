import { defineConfig } from '@playwright/test';

// Golden config: pinned 1280×720 viewport, headless, file://-served pages
// (no webServer needed — the journey uses relative links).
export default defineConfig({
  testDir: '.',
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
