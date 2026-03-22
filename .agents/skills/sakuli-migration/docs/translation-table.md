# Sakuli → Playwright + check-cep-vision Translation Table

Complete mapping of Sakuli v1/v2 APIs to their Playwright equivalents. Each entry shows the Sakuli original and the correct Playwright translation.

## Navigation

### `_navigateTo(url)`
```typescript
// Sakuli
_navigateTo("https://example.com/page");

// Playwright
await page.goto('https://example.com/page');
```

## Timing / Waiting

### `_wait(ms)`
```typescript
// Sakuli
_wait(2000);

// Playwright
await page.waitForTimeout(2000);
```

### `_pageIsStable(ms)`
```typescript
// Sakuli
_pageIsStable(2000);

// Playwright — wait for network to settle
await page.waitForLoadState('networkidle');
// or wait for a specific element that indicates stability
await page.waitForLoadState('domcontentloaded');
```

## Image-Based Steps

### `screen.find(image)`
```typescript
// Sakuli — locate an image on screen
const region = await screen.find("button.png");

// Playwright — locate by image (single-shot, no throw on not-found)
const result = await vision.locateByImage(page, 'assets/button.png', {
  region: 'main',
});
```

### `screen.find(image).click()` / `region.click()`
```typescript
// Sakuli
await screen.find("submit.png").click();

// Playwright
await vision.clickByImage(page, 'assets/submit.png', {
  region: 'main',
});
```

### `screen.find(image).mouseMove().click().type(text)`
```typescript
// Sakuli — find field by image, click, then type
await screen.find("name.png").mouseMove().click().type("Alice");

// Playwright — typeByImage does click + keyboard.type in one call
await vision.typeByImage(page, 'assets/name-row.png', 'Alice', {
  region: 'main',
  clickOffset: { x: 280, y: 18 },
});
```

### `region.sleepMs(ms).click()`
```typescript
// Sakuli — wait before clicking
await screen.find("slow-btn.png").sleepMs(500).click();

// Playwright — explicit wait, then click by image
await page.waitForTimeout(500);
await vision.clickByImage(page, 'assets/slow-btn.png', {
  region: 'main',
});
```

### `env.setSimilarity(n)`
```typescript
// Sakuli — lower match threshold globally
env.setSimilarity(0.7);

// Playwright — set confidence per-call (prefer region narrowing instead)
await vision.clickByImage(page, 'assets/weak-template.png', {
  confidence: 0.7,  // Only lower if you cannot improve the template
  region: 'main',
});
// WARNING: Lowering confidence is usually the wrong fix.
// Better: re-capture template, narrow region, or use clickOffset.
```

## DOM-Based Steps (Sahi API)

### `_link(text)`
```typescript
// Sakuli
_click(_link("Impressum"));

// Playwright
await page.getByRole('link', { name: 'Impressum' }).click();
```

### `_button(text)`
```typescript
// Sakuli
_click(_button("Submit"));

// Playwright
await page.getByRole('button', { name: 'Submit' }).click();
```

### `_heading1(text)` / `_heading2(text)` / `_heading3(text)`
```typescript
// Sakuli
_assertExists(_heading1("Welcome"));

// Playwright
await expect(page.getByRole('heading', { level: 1 })).toContainText('Welcome');
```

### `_span(text)`
```typescript
// Sakuli
_click(_span("Status"));

// Playwright
await page.locator('span', { hasText: 'Status' }).click();
// or
await page.getByText('Status').click();
```

### `_div(selector)`
```typescript
// Sakuli
_click(_div("content"));

// Playwright
await page.locator('div#content').click();
// or for class-based
await page.locator('div.content').click();
```

### `_textbox(selector)`
```typescript
// Sakuli
_setValue(_textbox("username"), "testuser");

// Playwright
await page.locator('input[name="username"]').fill('testuser');
// or
await page.getByLabel('Username').fill('testuser');
```

### `_textarea(selector)`
```typescript
// Sakuli
_setValue(_textarea("message"), "Hello world");

// Playwright
await page.locator('textarea[name="message"]').fill('Hello world');
```

### `_submit(selector)`
```typescript
// Sakuli
_click(_submit("Login"));

// Playwright
await page.locator('input[type="submit"][value="Login"]').click();
```

### `_paragraph(text)`
```typescript
// Sakuli
_assertExists(_paragraph("Terms and Conditions"));

// Playwright
await expect(page.locator('p', { hasText: 'Terms and Conditions' })).toBeVisible();
```

### `_strong(text)`
```typescript
// Sakuli
_assertExists(_strong("Important"));

// Playwright
await expect(page.locator('strong', { hasText: 'Important' })).toBeVisible();
```

### `_count(type, pattern)`
```typescript
// Sakuli — count matching elements
const n = _count("_link", "/product/");

// Playwright
const count = await page.locator('a[href*="product"]').count();
```

### `_in(region)` — Scoped Selection
```typescript
// Sakuli — find element within a container
_click(_link("Edit", _in(_div("row-1"))));

// Playwright — scoped locator
await page.locator('#row-1').getByRole('link', { name: 'Edit' }).click();
```

## Actions

### `_click(locator)`
```typescript
// Sakuli
_click(_link("Home"));

// Playwright
await page.getByRole('link', { name: 'Home' }).click();
```

### `_setValue(element, value)`
```typescript
// Sakuli
_setValue(_textbox("email"), "user@example.com");

// Playwright
await page.locator('input[name="email"]').fill('user@example.com');
```

### `_focus(element)`
```typescript
// Sakuli
_focus(_textbox("search"));

// Playwright
await page.locator('input[name="search"]').focus();
```

### `_mouseOver(element)`
```typescript
// Sakuli
_mouseOver(_link("Menu"));

// Playwright
await page.getByRole('link', { name: 'Menu' }).hover();
```

### `_highlight(element, ms)`
```typescript
// Sakuli — visual highlight for debugging
_highlight(_link("Target"), 2000);

// Playwright + check-cep-vision
await vision.highlightLocator(
  page.getByRole('link', { name: 'Target' }),
  { highlightMs: 2000 },
);
```

## Assertions

### `_assertExists(element)`
```typescript
// Sakuli
_assertExists(_heading1("Dashboard"));

// Playwright
await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible();
```

### `_exists(locator)`
```typescript
// Sakuli — boolean check
if (_exists(_link("Logout"))) { ... }

// Playwright
if (await page.getByRole('link', { name: 'Logout' }).isVisible()) { ... }
```

## Keyboard

### `env.paste(text)`
```typescript
// Sakuli — paste from clipboard
env.paste("long text content");

// Playwright — type simulates keystrokes, fill sets value directly
await page.keyboard.type('long text content');
// or for input fields:
await page.locator('#target').fill('long text content');
```

### `env.keyDown(key)` / `env.keyUp(key)`
```typescript
// Sakuli
env.keyDown("CTRL");
env.keyDown("A");
env.keyUp("A");
env.keyUp("CTRL");

// Playwright
await page.keyboard.down('Control');
await page.keyboard.press('a');
await page.keyboard.up('Control');
// or simpler:
await page.keyboard.press('Control+a');
```

## Framework / Lifecycle

### `new TestCase(name)` / `testCase.handleException(e)` / `testCase.saveResult()`
```typescript
// Sakuli — test lifecycle
const testCase = new TestCase("Login Test");
try {
  // ... test steps ...
} catch (e) {
  testCase.handleException(e);
} finally {
  testCase.saveResult();
}

// Playwright — handled automatically by the test runner
import { test, expect } from '@playwright/test';
test('Login Test', async ({ page }) => {
  // ... test steps ...
  // No try/catch needed — Playwright handles failures and reporting
});
```

### `new Environment()`
```typescript
// Sakuli — create environment for keyboard/screen access
const env = new Environment();

// Playwright — not needed. Use page.keyboard, page.mouse directly.
// The page fixture provides all interaction methods.
```

## Popup / Multi-Window

### `driver.getAllWindowHandles()` / `driver.switchTo().window(handle)`
```typescript
// Sakuli — switch to popup window
const handles = await driver.getAllWindowHandles();
await driver.switchTo().window(handles[1]);

// Playwright — wait for new page event
const [popup] = await Promise.all([
  page.context().waitForEvent('page'),
  page.getByRole('link', { name: 'Open Popup' }).click(),
]);
await popup.waitForLoadState();
// Now use 'popup' instead of 'page' for popup interactions
```
