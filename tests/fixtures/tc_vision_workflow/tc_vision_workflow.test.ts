import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';

/**
 * tc_vision_workflow — Sakuli-style multi-step visual login workflow.
 *
 * Simulates a realistic login flow using only vision helpers (no DOM selectors
 * for interactions). The test:
 *   1. Renders a login page with username, password, and submit button
 *   2. Captures templates for each interactive element
 *   3. Reloads the page (proves vision matching is independent of DOM state)
 *   4. Uses typeByImage for username
 *   5. Uses typeByImage for password
 *   6. Uses clickByImage for submit
 *   7. Asserts the form was submitted
 *
 * All interactions use only vision helpers — no DOM selectors.
 *
 * Validates: SC-001, SC-002
 */

const LOGIN_PAGE_HTML = `
  <html><body style="margin:0; display:flex; justify-content:center; align-items:center; height:100vh; background:#f1f5f9; font-family:Arial,sans-serif;">
    <div style="background:white; padding:40px; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.1); width:350px;">
      <h2 style="text-align:center; color:#1e293b; margin-bottom:24px;">Login</h2>
      <form id="login-form" onsubmit="event.preventDefault(); window.__formSubmitted={user:document.getElementById('username').value, pass:document.getElementById('password').value};">
        <div style="margin-bottom:16px;">
          <label style="display:block; margin-bottom:6px; color:#475569; font-size:14px;">Username</label>
          <input id="username" type="text" placeholder="Enter username"
            style="width:100%; padding:10px 12px; font-size:15px; font-family:Arial,sans-serif;
                   border:2px solid #cbd5e1; border-radius:6px; box-sizing:border-box;" />
        </div>
        <div style="margin-bottom:24px;">
          <label style="display:block; margin-bottom:6px; color:#475569; font-size:14px;">Password</label>
          <input id="password" type="password" placeholder="Enter password"
            style="width:100%; padding:10px 12px; font-size:15px; font-family:Arial,sans-serif;
                   border:2px solid #cbd5e1; border-radius:6px; box-sizing:border-box;" />
        </div>
        <button id="submit-btn" type="submit"
          style="width:100%; padding:12px; background:#2563eb; color:white;
                 border:none; border-radius:8px; font-size:16px; font-family:Arial,sans-serif; cursor:pointer;">
          Sign In
        </button>
      </form>
    </div>
  </body></html>
`;

test('multi-step login workflow using only vision helpers', async ({ page }, testInfo) => {
  // Phase 1: Render login page and capture templates
  await page.setContent(LOGIN_PAGE_HTML);
  await page.evaluate(() => document.fonts.ready);

  const usernameTemplate = testInfo.outputPath('username-template.png');
  const passwordTemplate = testInfo.outputPath('password-template.png');
  const submitTemplate = testInfo.outputPath('submit-template.png');

  await page.locator('#username').screenshot({ path: usernameTemplate, animations: 'disabled' });
  await page.locator('#password').screenshot({ path: passwordTemplate, animations: 'disabled' });
  await page.locator('#submit-btn').screenshot({ path: submitTemplate, animations: 'disabled' });

  // Phase 2: Reload page to break DOM state coupling
  await page.reload();
  await page.setContent(LOGIN_PAGE_HTML);
  await page.evaluate(() => document.fonts.ready);

  // Phase 3: Perform login using only vision helpers — no DOM selectors
  await vision.typeByImage(page, usernameTemplate, 'admin', { region: 'main' });
  await vision.typeByImage(page, passwordTemplate, 's3cret!Pass', { region: 'main' });
  await vision.clickByImage(page, submitTemplate, { region: 'main' });

  // Phase 4: Assert form was submitted with correct values
  const submitted = await page.evaluate(() => (window as any).__formSubmitted);
  expect(submitted).toBeDefined();
  expect(submitted.user).toBe('admin');
  expect(submitted.pass).toBe('s3cret!Pass');
});
