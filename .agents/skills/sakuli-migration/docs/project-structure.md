# Migrated Test Project Structure

Recommended directory layout for tests migrated from Sakuli to Playwright + check-cep-vision.

## Standard Layout

```
<test-name>/
├── <test-name>.test.ts     # Main test file — business scenario steps
├── functions/
│   └── index.ts            # Site-specific helpers (cookie consent, login, etc.)
├── assets/                 # Template images for vision-based steps
│   ├── submit-btn.png
│   ├── name-row.png
│   └── cookie-accept.png
└── variables/              # Optional: externalized test data
    └── config.ts           # URLs, credentials, expected values
```

## File Purposes

### `<test-name>.test.ts`
The main test file. Should read like the original Sakuli script — focused on business steps, not infrastructure.

```typescript
import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { cepLog, cepLogUrl } from 'check-cep-helpers';
import { acceptCookies } from './functions';

test.use({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });

test('form submission flow', async ({ page }) => {
  await page.goto('https://example-app.test/form');
  cepLogUrl(page);

  await acceptCookies(page);

  // Business steps follow...
});
```

### `functions/index.ts`
Site-specific helper functions. Keeps the main test clean.

```typescript
import { Page } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { cepLog } from 'check-cep-helpers';

export async function acceptCookies(page: Page): Promise<void> {
  // Site-specific cookie consent handling
}

export async function loginAsTestUser(page: Page): Promise<void> {
  // Site-specific login flow
}
```

**Put in functions/**: Cookie consent, login helpers, site-specific navigation shortcuts.
**Do NOT put in functions/**: Generic click/fill/highlight — that belongs in check-cep-vision.

### `assets/`
PNG template images captured under the standard render baseline (1280x720, DPR 1, animations disabled).

Naming conventions:
- Field rows: `first-name-row.png`, `email-row.png` (include label + input)
- Buttons: `submit-btn.png`, `next-btn.png` (include button text)
- Icons: `settings-icon.png`, `search-icon.png`
- Cookie: `cookie-accept.png` (tight crop of accept button)

### `variables/` (optional)
Externalized test data for tests that run against multiple environments.

```typescript
// variables/config.ts
export const config = {
  baseUrl: 'https://example-app.test',
  testUser: { name: 'Max', email: 'max@example.com' },
};
```

## Mapping from Sakuli Structure

| Sakuli | Playwright |
|--------|-----------|
| `testcases/<name>/sakuli.ts` | `<name>/<name>.test.ts` |
| `testcases/<name>/*.png` | `<name>/assets/*.png` |
| Inline helper functions | `<name>/functions/index.ts` |
| `testsuite.properties` | `playwright.config.ts` (at test root) |

## Import Patterns

```typescript
// Vision library (pre-installed in container)
import { vision } from 'check-cep-vision';

// Logging helpers (pre-installed in container)
import { cepLog, cepLogLocated, cepLogPress, cepLogType, cepLogWait, cepLogUrl } from 'check-cep-helpers';

// Playwright test framework (pre-installed in container)
import { test, expect } from '@playwright/test';

// Site-specific helpers (relative import)
import { acceptCookies } from './functions';
```
