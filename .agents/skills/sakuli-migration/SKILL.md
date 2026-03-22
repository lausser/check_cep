---
name: sakuli-migration
description: Expert guidance for migrating Sakuli v1 and v2 browser test scripts to Playwright running inside the check_cep container. Use when converting Sakuli tests, translating Sahi DOM selectors, or preserving SikuliX image-based steps as check-cep-vision calls. Triggers on Sakuli migration, Sakuli to Playwright, Sahi selector, SikuliX, screen.find, _click, _setValue, _navigateTo, or test migration.
---

# sakuli-migration: Migrating Sakuli Tests to Playwright + check-cep-vision

Step-by-step guidance for faithfully converting Sakuli v1/v2 browser monitoring scripts into Playwright tests that run inside the `check_cep` container. The migration preserves the original locator strategy: image-based Sakuli steps become `check-cep-vision` calls, DOM-based Sakuli steps become Playwright locators.

## The Most Important Rule

> **Migrate locator intent, not just test outcome.**

This means:
- If the Sakuli step used **image matching** (`screen.find()`), the Playwright step MUST use `vision.clickByImage()` or `vision.typeByImage()` — NOT a DOM selector.
- If the Sakuli step used **DOM/HTML selection** (`_click()`, `_setValue()`), the Playwright step MUST use `page.locator()` — NOT image matching.
- If the Sakuli step had **image-first with DOM fallback**, use `vision.clickByImageOr()` or `vision.typeByImageOr()`.

### What "Cheating" Looks Like

Replacing `screen.find("plz.png")` with `page.locator('input[name*="plz"]')` is cheating — the original author did not rely on DOM structure there. The migrated example falsely suggests the migration naturally knows the DOM.

## When to Use

- Migrating any Sakuli v1 (Sahi/SikuliX) or v2 (async) test script to Playwright
- Converting `.js` or `.ts` files that contain Sakuli APIs: `_click`, `_setValue`, `_navigateTo`, `screen.find`, `env.paste`, `TestCase`, `Environment`
- Translating Sakuli monitoring tests into `check_cep` container tests

## When NOT to Use

- Writing new Playwright tests from scratch (use [check-cep-vision](../check-cep-vision/SKILL.md) or [playwright-skill](../playwright-skill/SKILL.md) instead)
- Analyzing or understanding Sakuli scripts without migrating them (use the `sakuli-expert-ultimate` skill at `.claude/skills/sakuli-expert-ultimate/SKILL.md`)

## Quick Start

Given a Sakuli script:
```javascript
// Sakuli v1
_navigateTo("https://example.com/form");
_setValue(_textbox("name"), "Alice");
await screen.find("submit.png").click();
```

The migrated Playwright test:
```typescript
import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';

test('form submission', async ({ page }) => {
  // DOM step stays DOM (Sakuli _navigateTo → page.goto)
  await page.goto('https://example.com/form');

  // DOM step stays DOM (Sakuli _setValue/_textbox → Playwright locator)
  await page.locator('input[name="name"]').fill('Alice');

  // Image step stays image (Sakuli screen.find → vision.clickByImage)
  await vision.clickByImage(page, 'assets/submit.png', { region: 'main' });

  await expect(page).toHaveURL(/success/);
});
```

## Migration Workflow

1. **Read** the original Sakuli script end-to-end
2. **Classify** each step: image-based, DOM-based, or framework boilerplate
3. **Translate** each step using the [Translation Table](docs/translation-table.md)
4. **Create** the project structure: `test.ts`, `functions/`, `assets/`
5. **Capture** fresh template images for all image-based steps (use the render baseline)
6. **Handle** cookie consent banners as a dedicated helper in `functions/`
7. **Test** inside the container — verify each step matches the original intent

## Core Migration Rules

### Rule 1: Preserve Locator Intent
Image steps → `vision.clickByImage()` / `vision.typeByImage()`
DOM steps → `page.locator()` / `page.getByRole()` / `page.getByText()`

### Rule 2: No Route Shortcuts
If the Sakuli script navigates home → clicks through menus → reaches a form, do NOT shortcut to the form URL directly. The original path is part of the test.

### Rule 3: Fallback Only Where It Already Existed
Only add `clickByImageOr()` / `typeByImageOr()` if the original Sakuli script already had a fallback mechanism. Do NOT add fallback to strict image steps.

### Rule 3a: Pragmatic Fallback Exception
When image matching becomes **unstable, too expensive to maintain, or visually impossible** on the live site (animated controls, rotating hero sections, frequent CSS redesigns), a documented switch to DOM or hybrid locators is permitted. The key: the fallback must be an **intentional, documented engineering decision**, not silent cheating. Add a comment explaining why image matching was abandoned for that step.

### Rule 4: Site-Specific Helpers in `functions/`
Cookie consent, login flows, and other site-specific annoyances go into `functions/index.ts`. Generic behavior stays in `check-cep-vision`.

### Rule 5: Highlight for Visual Feedback
Sakuli users expect visual highlighting. Use `vision.highlightLocator()` for DOM elements and `vision.highlightByImage()` for image elements to restore Sakuli's visual transparency.

### Rule 6: Old Assets May Need Re-Capture
Legacy Sakuli image assets were captured under different rendering conditions. Re-capture templates under the standard baseline (1280x720, DPR 1, animations disabled) inside the container.

### Rule 7: Flag Non-Migrateable Steps
If the Sakuli script uses SikuliX desktop automation (`Environment`, `Region` for desktop windows) with no browser equivalent, flag those steps as "not migrateable to Playwright" — do NOT silently drop them.

### Rule 8: Multi-Stage Image Location
If a small template cannot be found reliably on the full page, use a staged approach:
1. Find a larger anchor image first
2. Use the anchor's position to derive a region
3. Search for the smaller target within that narrowed region

This is a standard migration technique, not a last resort. See [examples/staged-anchor](../check-cep-vision/examples/staged-anchor.ts).

## Decision Tree: How to Translate Each Step

```
What did the original Sakuli step do?
├── Navigate → page.goto(url)
├── Wait → page.waitForTimeout(ms) or page.waitForLoadState()
├── DOM click (_click, _link, _button) → page.locator(...).click()
├── DOM type (_setValue, _textbox) → page.locator(...).fill(value)
├── Image find+click (screen.find().click()) → vision.clickByImage(page, template, options)
├── Image find+type (screen.find().type()) → vision.typeByImage(page, template, text, options)
├── Image+DOM fallback → vision.clickByImageOr / vision.typeByImageOr
├── Assert exists (_assertExists) → expect(locator).toBeVisible()
├── Keyboard (env.paste, keyDown/Up) → page.keyboard.type / press
├── Popup (switchTo().window) → page.context().waitForEvent('page')
└── Framework (TestCase, saveResult) → Remove — Playwright handles this
```

## Migration Definition of Done

A migration is complete when:

- [ ] The Sakuli scenario flow is preserved (or deviations are documented with rationale)
- [ ] Each step's locator strategy is classified: strict image / image+DOM fallback / pure DOM / non-migrateable
- [ ] Cookie/overlay handling is verified and extracted to `functions/`
- [ ] The test runs successfully inside the `check_cep` container
- [ ] Debug artifacts are available for image-based steps (debugDir/debugLabel set)
- [ ] A human familiar with the original Sakuli script can read the migration and understand why each locator choice was made

## Anti-Patterns

**DO NOT** replace all image steps with DOM selectors. This defeats the purpose of a faithful migration.

**DO NOT** add `clickByImageOr()` fallbacks to every image step. Only add fallback where the original Sakuli script already had one, or where the live site has made image matching impractical (Rule 3a). In the latter case, document why.

**DO NOT** hard-code absolute pixel coordinates for regions. Derive regions from the 1280x720 viewport or use named presets.

**DO NOT** include customer-specific URLs, company names, or form field values in migration examples. Anonymize everything.

**DO NOT** put generic click/fill/highlight logic in `functions/index.ts`. That belongs in `check-cep-vision`.

## References

- [Translation Table](docs/translation-table.md) — 30+ Sakuli API → Playwright mappings with code snippets
- [Migration Rules](docs/migration-rules.md) — Detailed core rules with examples and rationale
- [Cookie Consent Guide](docs/cookie-consent.md) — Multi-layer cookie banner handling patterns
- [Project Structure](docs/project-structure.md) — Directory layout for migrated tests
- [Image Step Example](examples/image-step.ts) — screen.find → vision.clickByImage
- [DOM Step Example](examples/dom-step.ts) — _click/_setValue → page.locator
- [Fallback Step Example](examples/fallback-step.ts) — Image-first + DOM fallback
- [Cookie Handler Example](examples/cookie-handler.ts) — Site-specific consent helper
- [Complete Migration Example](examples/complete-migration.ts) — Full before/after migration

## Related Skills

- [check-cep-vision](../check-cep-vision/SKILL.md) — Complete vision API reference, template creation guide, troubleshooting
- [playwright-skill](../playwright-skill/SKILL.md) — General Playwright test authoring
- `sakuli-expert-ultimate` at `.claude/skills/sakuli-expert-ultimate/SKILL.md` — Deep Sakuli analysis and comprehension (for understanding scripts before migration)
