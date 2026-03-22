---
name: check-cep-vision
description: Expert guidance for writing Playwright tests with check-cep-vision image-based locators. Use when writing tests that need to find, click, or type into UI elements by visual template matching instead of DOM selectors. Triggers on check-cep-vision, image matching, template matching, visual locator, clickByImage, typeByImage, vision-based testing, locateByImage, waitForImage, highlightByImage, or hybrid fallback.
---

# check-cep-vision: Image-Based Locators for Playwright

A container-bundled library that adds image-based element location to Playwright using OpenCV template matching. Test authors locate, click, type, and highlight UI elements by providing a PNG screenshot of the target instead of a CSS/ARIA selector.

## When to Use

Use `check-cep-vision` when:

- The page uses dynamically generated CSS class names (e.g., CSS modules, Tailwind JIT)
- The target is a canvas, WebGL scene, or embedded PDF with no DOM elements
- You are migrating Sakuli/SikuliX tests that were always image-driven
- The test validates what the **user sees**, not just what the HTML contains
- Multiple similar inputs exist and visual context (label + field) disambiguates them

## When NOT to Use

Do **not** use vision locators when:

- A stable DOM selector exists (`data-testid`, ARIA role, semantic label)
- The element has accessible text that Playwright's `getByRole()` or `getByText()` can find
- The page is simple, stable HTML — DOM locators are faster and easier to maintain

**Default recommendation**: Use DOM locators first. Add vision only when DOM is insufficient.

## Quick Start

```typescript
import { test, expect } from '@playwright/test';
import { vision } from 'check-cep-vision';

test('click the submit button by image', async ({ page }) => {
  await page.goto('https://example.com/form');

  // Click a button found by its visual appearance
  await vision.clickByImage(page, 'assets/submit-btn.png', {
    region: 'main',
  });

  await expect(page).toHaveURL(/success/);
});
```

## Import

```typescript
import { vision } from 'check-cep-vision';
```

The module is pre-installed in the check_cep container at `/home/pwuser/node_modules/check-cep-vision/`. No npm install needed inside the container.

## Core Concepts

### Template Images — Your Visual Selectors

A template is a tightly cropped PNG screenshot of the target element. Templates are committed alongside the test in an `assets/` directory.

**Good template**: Include the label + control together so the template is visually unique.

```
Good (label + input):              Bad (bare input):
┌─────────────────────────────┐    ┌────────────────────┐
│  Name    [________________] │    │ [________________]  │
└─────────────────────────────┘    └────────────────────┘
Unique — "Name" text is part       Generic — matches any
of the pixel pattern               text input on the page
```

**Render baseline**: Templates MUST be captured under the standard baseline:
- Viewport: **1280 x 720**
- Device scale factor: **1** (no HiDPI)
- Animations: **disabled**
- Caret: **hidden**

See [examples/playwright.config.ts](examples/playwright.config.ts) for the standard configuration.

### Regions — Tell the System Where to Look

Region narrowing is the single biggest reliability lever. Always provide a region.

**Named presets** (based on 1280x720 viewport):

| Preset | Area |
|--------|------|
| `'header'` | Top 18% of viewport |
| `'main'` | Center inset (10% from sides, 14% from top, 72% height) |
| `'footer'` | Bottom 20% of viewport |
| `'topLeft'` | Left half, top 35% |
| `'topRight'` | Right half, top 35% |
| `'left'` | Left half, full height |
| `'right'` | Right half, full height |

**Custom rectangle** for precise control:

```typescript
const FIRST_ROW = { x: 740, y: 230, width: 530, height: 65 };
await vision.clickByImage(page, 'assets/delete-btn.png', { region: FIRST_ROW });
```

**Default behavior** (no region specified): Uses a `main`-like center inset, NOT the full page. Use `{ fullPage: true }` for explicit full-page search.

**WARNING**: `region` and `fullPage` cannot be combined — the library rejects this as `invalid-options`.

### Click Offsets — When the Click Target Differs from the Match Center

For label+input templates, the match center lands on the label. Use `clickOffset` to shift the click into the input:

```typescript
await vision.typeByImage(page, 'assets/name-row.png', 'Alice', {
  region: 'main',
  clickOffset: { x: 300, y: 21 },  // Shift right into the input field
});
```

### Hybrid Fallback — Vision First, DOM Backup

When you want vision verification but need DOM resilience:

```typescript
await vision.typeByImageOr(
  page,
  'assets/name-row.png',
  'Alice',
  ['#name-input', 'input[name="name"]'],  // DOM fallback selectors
  { region: 'main', clickOffset: { x: 300, y: 21 } },
);
```

If the image match fails, it falls back to the first visible DOM selector.

### Highlighting — Visual Feedback for Debugging and Demos

All click/type/fill operations automatically highlight the found element before interaction (Sakuli-style visual feedback). Configure via:

- `highlightMs` option (per-call)
- `CEP_VISION_HIGHLIGHT_MS` environment variable (global default, in milliseconds)
- Default: 700ms

For DOM elements, use `vision.highlightLocator(locator)`.

## Decision Tree: Which Function to Use

```
Need to interact with the element?
├── Yes, click it
│   ├── Vision only → clickByImage(page, template, options)
│   └── Vision + DOM fallback → clickByImageOr(page, template, candidates, options)
├── Yes, type into it
│   ├── Vision only → typeByImage(page, template, text, options)
│   └── Vision + DOM fallback → typeByImageOr(page, template, text, selectors, options)
├── No, just check if it exists
│   ├── Boolean check → existsByImage(page, template, options)
│   ├── Wait for appearance → waitForImage(page, template, options)
│   └── Single locate → locateByImage(page, template, options)
└── No, just highlight it
    ├── By image → highlightByImage(page, template, options)
    └── By DOM locator → highlightLocator(locator, options)
```

## Anti-Patterns

**DO NOT** lower the confidence threshold to make a weak template match. Fix the template or narrow the region instead.

**DO NOT** use `fullPage: true` as the default. It increases ambiguity and CPU cost. Always prefer a named region preset or custom rectangle.

**DO NOT** capture templates at a different viewport size or DPR than the test runtime. This is the #1 cause of `not-found` failures.

**DO NOT** create templates of bare input fields without their labels. They all look identical and will produce `ambiguous` results.

**DO NOT** include dynamic content (timestamps, counters, animations) in templates. They change on every page load.

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `CEP_VISION_HIGHLIGHT_MS` | `700` | Global highlight duration (ms). Set to `0` to disable. |
| `CEP_VISION_DEBUG` | unset | When `1`, enables debug artifact writing |
| `BROWSER` | `chromium` | When `lightpanda`, vision functions throw or fall back to DOM |

## Companion Library: check-cep-helpers

Tests commonly import logging helpers alongside vision:

```typescript
import { cepLog, cepLogLocated, cepLogPress, cepLogType, cepLogWait, cepLogUrl, cepDebug } from 'check-cep-helpers';
```

| Function | Output |
|----------|--------|
| `cepLog(message)` | `[CEP+123ms] message` |
| `cepLogLocated(target)` | `[CEP+123ms] located element: target` |
| `cepLogType(target, value)` | `[CEP+123ms] typing string into target: value` |
| `cepLogPress(target)` | `[CEP+123ms] pressing button/link/option: target` |
| `cepLogWait(durationMs, reason)` | `[CEP+123ms] waiting 2000ms reason` |
| `cepLogUrl(page)` | `[CEP+123ms] current page url is https://...` |
| `cepDebug(message)` | `[CEPDBG] message` |

## References

- [API Reference](docs/api-reference.md) — Complete function signatures, options, return types, and constants
- [Template Guide](docs/template-guide.md) — How to capture, crop, and maintain template images
- [Vision Explainer](docs/vision-explainer.md) — How the two-stage matching pipeline works internally
- [Troubleshooting](docs/troubleshooting.md) — Diagnosing not-found, ambiguous, and baseline mismatch failures
- [Basic Click Example](examples/basic-click.ts) — Minimal clickByImage with region
- [Hybrid Fallback Example](examples/hybrid-fallback.ts) — typeByImageOr with DOM fallback
- [Region-Scoped Example](examples/region-scoped.ts) — Ambiguity resolution via region narrowing
- [Staged Anchor Example](examples/staged-anchor.ts) — Multi-stage anchor-then-target pattern
- [Capture Templates Script](examples/capture-templates.mjs) — Template capture script skeleton
- [Playwright Config](examples/playwright.config.ts) — Standard render baseline config

## Related Skills

- [playwright-skill](../playwright-skill/SKILL.md) — General Playwright test authoring (DOM selectors, assertions, page interactions)
- [sakuli-migration](../sakuli-migration/SKILL.md) — Migrating Sakuli tests to Playwright (uses check-cep-vision for image steps)
