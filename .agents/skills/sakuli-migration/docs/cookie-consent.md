# Cookie Consent Banner Handling

Cookie consent banners are the #1 source of migration failures on live sites. This guide covers the patterns for handling them in migrated Sakuli tests.

## Why Cookie Banners Matter

Cookie banners:
- Block clicks on underlying elements
- Cover content the test needs to interact with
- Create duplicate visible elements (e.g., "Impressum" appears both in the banner and in the footer)
- Change page layout until dismissed
- May appear asynchronously after page load

In Sakuli tests, consent was often handled via image matching on the accept button. The migration should preserve this approach.

## The Multi-Layer Strategy

Handle consent in a dedicated helper function with three layers of fallback:

### Layer 1: Image-First with DOM Fallback

```typescript
await vision.clickByImageOr(
  page,
  'assets/cookie-accept.png',  // Tight crop of the accept button
  [
    page.getByRole('button', { name: /accept|akzeptieren|agree/i }),
    page.locator('[data-testid="cookie-accept"]'),
  ],
  { region: 'main', timeoutMs: 3000 },
);
```

### Layer 2: Settings Path

Some sites require clicking "Settings" then "Accept All":

```typescript
await page.getByRole('button', { name: /settings|einstellungen/i }).click();
await page.getByRole('button', { name: /accept all|alle akzeptieren/i }).click();
```

### Layer 3: Graceful Absence

If no banner is found, the test continues — the banner may be absent or already dismissed.

## Template Creation for Consent Buttons

### Crop Tightly

Capture just the accept button, not the entire banner:

```
Good (button crop):                Bad (full banner):
┌────────────────────┐            ┌──────────────────────────────────┐
│  Accept All  ✓     │            │ We use cookies to improve...     │
└────────────────────┘            │ [Settings] [Accept All]          │
Unique, focused on                │ Read our privacy policy...       │
the actionable target             └──────────────────────────────────┘
                                  Too much noise, more likely to
                                  drift when text or spacing changes
```

### Capture Inside the Container

Consent banners render differently in different browsers and font environments. Always capture inside the container.

## Helper Function Pattern

Put the consent handler in `functions/index.ts`:

```typescript
import { Page } from '@playwright/test';
import { vision } from 'check-cep-vision';
import { cepLog } from 'check-cep-helpers';

export async function acceptCookies(page: Page): Promise<void> {
  try {
    await vision.clickByImageOr(
      page,
      'assets/cookie-accept.png',
      [
        page.getByRole('button', { name: /accept|akzeptieren/i }),
        page.locator('.cookie-banner .accept'),
      ],
      { region: 'main', timeoutMs: 3000 },
    );
    cepLog('Cookie consent accepted');
  } catch {
    cepLog('No cookie banner found');
  }
}
```

Call it early in every test:

```typescript
test('form check', async ({ page }) => {
  await page.goto('https://example.com');
  await acceptCookies(page);
  // ... rest of test
});
```

## When the Original Sakuli Used Image-Only

If the Sakuli script used `screen.find("accept_cookies.png").click()` without any DOM fallback, the migration should primarily use image matching:

```typescript
try {
  await vision.clickByImage(page, 'assets/cookie-accept.png', {
    region: 'main',
    timeoutMs: 3000,
  });
} catch {
  cepLog('Cookie banner not found (may be already dismissed)');
}
```

Only add DOM fallback if you need extra resilience against banner redesigns.

## Multi-Page Consent

Some sites show the consent banner again when navigating to a new page or opening a popup:

```typescript
// Check for consent after each navigation
await page.goto('https://example.com/page2');
await acceptCookies(page);  // May or may not find a banner

// Popups may have their own consent
const [popup] = await Promise.all([
  page.context().waitForEvent('page'),
  page.click('a[target="_blank"]'),
]);
await popup.waitForLoadState();
await acceptCookies(popup);  // Pass the popup page object
```

## Common Pitfalls

1. **Banner appears asynchronously**: Use `timeoutMs: 3000` or higher to wait for lazy-loaded banners
2. **Banner covers the target**: Always dismiss consent BEFORE interacting with other elements
3. **Hidden duplicate elements**: The banner creates duplicate "Impressum" or "Privacy" links — inspect the DOM to find the real visible target
4. **Multi-step consent**: Some GDPR-strict sites require clicking through settings before accepting
5. **Consent persisted**: If running tests with a persistent browser context, consent may already be dismissed from a previous test
