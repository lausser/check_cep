# Core Migration Rules

Detailed rules for faithfully migrating Sakuli v1/v2 scripts to Playwright + check-cep-vision. These rules ensure the migration preserves the original test's intent.

## Rule 1: Preserve Locator Intent

The most important rule. Each step must keep its original locator strategy.

| Original Sakuli Step | Migrated Playwright Step |
|---------------------|--------------------------|
| `screen.find("btn.png").click()` | `vision.clickByImage(page, 'assets/btn.png', ...)` |
| `_click(_link("Home"))` | `page.getByRole('link', {name: 'Home'}).click()` |
| Image with DOM fallback | `vision.clickByImageOr(page, template, candidates, ...)` |

### Why This Matters

- Preserves what the original author actually trusted
- Keeps the before/after comparison honest
- Makes the migrated example useful as training material
- Prevents "stealth modernization" that hides migration difficulty

### What Counts as Cheating

Replacing `screen.find("plz.png")` with `page.locator('input[name*="plz"]')` is cheating because:
- The Sakuli author did not rely on DOM structure
- The migration falsely implies DOM knowledge was available
- It undermines the purpose of demonstrating image-based migration

## Rule 2: No Route Shortcuts

If the Sakuli script reaches a page through navigation (home → menu → subpage → form), the Playwright migration must follow the same path.

**Wrong:**
```typescript
// Sakuli navigated: home → "Products" link → "Insurance" link → form
// DON'T shortcut to the form URL directly:
await page.goto('https://example.com/insurance/form');  // CHEATING
```

**Correct:**
```typescript
await page.goto('https://example.com');
await page.getByRole('link', { name: 'Products' }).click();
await page.getByRole('link', { name: 'Insurance' }).click();
// Now on the form page, following the original navigation path
```

### Why

- The navigation path IS part of the test
- Route shortcuts introduce knowledge the original test didn't have
- The original path may trigger different server-side behavior

## Rule 3: Fallback Only Where It Already Existed

Only use `clickByImageOr()` / `typeByImageOr()` when the original Sakuli script already had a fallback mechanism.

**Original had fallback:**
```javascript
// Sakuli
try { await screen.find("next.png").click(); }
catch { _click(_button("Next")); }
```
→ Use `vision.clickByImageOr(page, 'assets/next.png', [page.getByRole('button', {name: 'Next'})], ...)`

**Original was strict image-only:**
```javascript
// Sakuli
await screen.find("vorname.png").type("Max");
```
→ Use `vision.typeByImage(page, 'assets/vorname-row.png', 'Max', ...)` — NO fallback.

### Why

Adding fallback to every step silently changes the original test strategy. If the original author used strict image matching, they had a reason.

### Pragmatic Exception (Rule 3a)

When a live site makes image matching **unstable, too expensive to maintain, or visually impossible** — animated controls, rotating hero banners, frequent corporate CSS redesigns — switching a strict image step to hybrid or pure DOM is permitted. This is not cheating; it is senior engineering.

The requirement: the switch must be a **conscious, documented decision**:

```typescript
// Original Sakuli: await screen.find("hero-cta.png").click();
// Pragmatic fallback: hero banner rotates on every page load — image matching
// is unstable. DOM locator is the reliable engineering choice here.
await page.getByRole('button', { name: 'Get Started' }).click();
```

If you find yourself adding fallback to more than ~30% of image steps, the site may have changed so much that a fresh test design (not a migration) would be more honest and maintainable.

## Rule 4: Site-Specific Helpers in `functions/`

Put site-specific annoyances in `functions/index.ts`:
- Cookie consent dismissal
- Login pre-steps
- Popup/modal handling specific to the site

Keep the main test file focused on the business scenario steps.

**Good structure:**
```typescript
// functions/index.ts
export async function acceptCookies(page: Page) { ... }
export async function loginAsTestUser(page: Page) { ... }

// test.ts
import { acceptCookies, loginAsTestUser } from './functions';
test('checkout flow', async ({ page }) => {
  await page.goto('https://example.com');
  await acceptCookies(page);
  await loginAsTestUser(page);
  // ... actual business steps
});
```

### Why

- The test file reads like the Sakuli script (business steps only)
- Annoyance handling is visible but not distracting
- Generic behavior stays in check-cep-vision, not in functions/

## Rule 5: Use Highlighting for Visual Feedback

Sakuli highlights found elements visually. Preserve this in the migration:

```typescript
// For DOM elements
await vision.highlightLocator(page.getByRole('link', { name: 'Home' }));

// For image-based steps — highlighting is automatic in clickByImage/typeByImage

// Global control via environment variable
// CEP_VISION_HIGHLIGHT_MS=1500 (milliseconds, 0 to disable)
```

### Why

- Lowers psychological resistance for Sakuli authors
- Makes headed/demo runs visually understandable
- Helps debug which element was found

## Rule 6: Re-Capture Templates Under Standard Baseline

Legacy Sakuli templates were captured under different rendering conditions. They often fail in the Playwright container because:
- Different viewport size
- Different DPR (device pixel ratio)
- Different font rendering
- Different anti-aliasing

**Action:** Re-capture all templates inside the container at:
- 1280x720 viewport
- DPR 1
- Animations disabled
- Caret hidden

See the [capture-templates.mjs](../../check-cep-vision/examples/capture-templates.mjs) script.

## Rule 7: Flag Non-Migrateable Steps

If the Sakuli script uses SikuliX desktop automation features that have no browser equivalent:

```javascript
// Sakuli — desktop automation (no browser equivalent)
const env = new Environment();
env.type(Key.TAB);  // System keyboard
const region = new Region(100, 200, 300, 50);  // Desktop coordinates
region.click();  // Desktop mouse click
```

**Action:** Add a clear comment in the migrated test:

```typescript
// ⚠️ NOT MIGRATEABLE: Original Sakuli step used desktop automation
// (SikuliX Region/Environment) which has no browser equivalent.
// Original: env.type(Key.TAB) — system-level keyboard input
// Manual intervention required to determine browser equivalent.
```

Do NOT silently drop these steps.

## Rule 8: Multi-Stage Image Location

When a small template can't be found reliably:
1. Find a larger anchor image first
2. Derive a region from the anchor position
3. Search for the small target within that region

This is a standard migration technique. See [staged-anchor example](../../check-cep-vision/examples/staged-anchor.ts).

## Debugging a Migration

When a migrated step fails:
1. **Classify** the step: was it image-based or DOM-based in the original?
2. **Inspect** the live page with browser DevTools (accessibility tree, visible elements)
3. **Check** for cookie banners, popups, or overlays blocking the target
4. **Verify** template quality (captured under correct baseline?)
5. **Narrow** the region if ambiguity is the issue
6. **Only then** consider adjusting confidence or adding fallback

Do NOT blindly iterate by changing locators — inspect the actual page state first.
