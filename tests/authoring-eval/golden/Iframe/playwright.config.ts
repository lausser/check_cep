import { defineConfig } from '@playwright/test';

// The iframe golden is the one HTTP-served pair: parent and child must share a
// real, same origin for cross-frame DOM access (research R7). The pages travel
// with this test (index.html + frame.html) and a tiny static server serves them.
const PORT = 8092;

export default defineConfig({
  testDir: '.',
  timeout: 30000,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
    baseURL: `http://127.0.0.1:${PORT}`,
  },
  webServer: {
    command: `python3 -m http.server ${PORT}`,
    url: `http://127.0.0.1:${PORT}/index.html`,
    reuseExistingServer: true,
    timeout: 20000,
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
