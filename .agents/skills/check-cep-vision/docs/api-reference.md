# check-cep-vision API Reference

Complete reference for every public function, type, and constant exported by `check-cep-vision`. This document is the source of truth for AI coding agents writing Playwright tests with image-based locators.

---

## Import

```typescript
import { vision } from 'check-cep-vision';
```

The module is pre-installed in the check_cep container at `/home/pwuser/node_modules/check-cep-vision/`. No npm install needed.

---

## Types

### RegionPreset

```typescript
type RegionPreset = 'header' | 'main' | 'footer' | 'topLeft' | 'topRight' | 'left' | 'right';
```

Named viewport regions based on a 1280x720 viewport. See [SKILL.md](../SKILL.md) for the pixel areas each preset covers.

### RectRegion

```typescript
interface RectRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}
```

Custom rectangular search area in viewport coordinates (pixels from top-left).

### ClickOffset

```typescript
interface ClickOffset {
  x: number;
  y: number;
}
```

Pixel offset applied to the click point. When provided, the click lands at `match.x + offset.x`, `match.y + offset.y` (offset from the **top-left** corner of the match, not from center). When omitted, the click lands at `match.centerX`, `match.centerY`.

### VisionOptions

```typescript
interface VisionOptions {
  region?: RegionPreset | RectRegion;   // Where to search (named preset or custom rectangle)
  fullPage?: boolean;                   // Search entire page (cannot combine with region)
  confidence?: number;                  // Minimum combined score to accept (default: 0.9)
  ambiguityGap?: number;               // Min gap between best and second candidate (default: 0.03)
  timeoutMs?: number;                   // Polling timeout for wait-based functions (default: 1200)
  pollMs?: number;                      // Polling interval (default: 100)
  clickOffset?: ClickOffset;           // Shift the click point from match top-left
  debugDir?: string;                    // Write debug artifacts to this directory
  debugLabel?: string;                  // Prefix for debug artifact filenames
  scales?: number[];                    // Scale variants to try (default: [0.97, 1.0, 1.03])
  maxCandidates?: number;              // Max grayscale candidates to verify (default: 4)
  highlightMs?: number;                // Highlight duration in ms (default: 700 or CEP_VISION_HIGHLIGHT_MS)
  highlightColor?: string;             // Highlight border color (default: '#ffb703')
  highlightFillColor?: string;         // Highlight fill color (default: 'rgba(255, 183, 3, 0.14)')
  scrollIntoView?: boolean;            // Scroll element into view before interaction (default: true)
}
```

**Constraint:** `region` and `fullPage` cannot both be set. The library rejects this combination with reason `invalid-options`.

### MatchCandidate

```typescript
interface MatchCandidate {
  x: number;            // Top-left X in viewport coordinates
  y: number;            // Top-left Y in viewport coordinates
  width: number;        // Template width at matched scale
  height: number;       // Template height at matched scale
  score: number | null; // Grayscale match score (0-1)
  scale: number;        // Scale factor that produced this match
  colorScore: number | null;     // Color verification score (0-1)
  combinedScore: number | null;  // Weighted: 0.45*gray + 0.55*color
  centerX: number;      // Center X in viewport coordinates
  centerY: number;      // Center Y in viewport coordinates
}
```

### MatchResult

```typescript
interface MatchResult {
  found: boolean;                      // true if match accepted
  reason: string;                      // See "Reason values" below
  confidence: number;                  // Confidence threshold used
  ambiguityGap: number;               // Ambiguity gap threshold used
  region: RectRegion | null;           // Effective search region (alias for effectiveRegion)
  requestedRegion: RectRegion | null;  // Original requested region before clipping
  effectiveRegion: RectRegion | null;  // Actual region after clipping to viewport
  regionMode: string;                  // 'preset:header', 'custom', 'default-main-inset', 'full-page', etc.
  regionWasClipped: boolean;           // true if region was clipped to viewport bounds
  bestCandidate: MatchCandidate | null;        // Best match in viewport coordinates
  bestCandidateLocal: MatchCandidate | null;   // Best match in region-local coordinates
  secondCandidate: MatchCandidate | null;      // Second-best in viewport coordinates
  secondCandidateLocal: MatchCandidate | null; // Second-best in region-local coordinates
  message: string;                     // Human-readable status/error message
}
```

**Reason values:**

| Reason | Meaning |
|--------|---------|
| `'found'` | Match accepted (score >= confidence, gap >= ambiguityGap) |
| `'not-found'` | No candidate scored above confidence threshold |
| `'ambiguous'` | Top two candidates too close (gap < ambiguityGap) |
| `'invalid-template'` | Template image is empty or has zero opaque pixels |
| `'invalid-region'` | Region is outside viewport or has zero area |
| `'invalid-options'` | Conflicting options (e.g., region + fullPage) |
| `'invalid-size'` | Template larger than search region |
| `'scoring-failed'` | Internal error during score computation |
| `'unreadable-template'` | Template file cannot be read or decoded |

**Terminal reasons** (cause immediate failure, no retry): `invalid-size`, `invalid-template`, `invalid-region`, `invalid-options`, `scoring-failed`, `unreadable-template`.

### ClickResult

```typescript
interface ClickResult extends MatchResult {
  clickPoint: { x: number; y: number };  // Where the click landed (after offset)
}
```

Extends `MatchResult` with the actual viewport coordinates where the mouse click was dispatched.

### StrategyResult

```typescript
interface StrategyResult {
  strategy: 'vision' | 'dom';   // Which strategy succeeded
  result?: ClickResult;         // Vision result (only present when strategy='vision')
}
```

Returned by hybrid functions (`clickByImageOr`, `typeByImageOr`). The `result` field is only populated when vision succeeded.

---

## Functions

### Core Vision Functions

---

#### `canScreenshot()`

```typescript
vision.canScreenshot(): boolean
```

Returns `true` if the browser can take screenshots. Returns `false` when `BROWSER=lightpanda` (a DOM-only browser with no rendering pipeline). Use this to guard vision calls in tests that must also run on Lightpanda.

**Parameters:** None.

**Returns:** `boolean`

**Throws:** Never.

```typescript
if (vision.canScreenshot()) {
  await vision.clickByImage(page, 'assets/btn.png');
} else {
  await page.click('#submit');
}
```

---

#### `locateByImage()`

```typescript
vision.locateByImage(
  page: Page,
  templatePath: string,
  options?: VisionOptions
): Promise<MatchResult>
```

Single-shot locate. Takes one screenshot and attempts to find the template. Does **not** throw on `not-found` or `ambiguous` -- returns a `MatchResult` with `found: false`. **Does** throw for the Lightpanda guard (no visual browser).

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `page` | `Page` | Playwright page instance |
| `templatePath` | `string` | Path to the template PNG file |
| `options` | `VisionOptions` | Optional matching configuration |

**Returns:** `Promise<MatchResult>` -- Always resolves. Check `result.found` and `result.reason`.

**Throws:** When `BROWSER=lightpanda` (no visual browser).

```typescript
const result = await vision.locateByImage(page, 'assets/logo.png', { region: 'header' });
if (result.found) {
  console.log('Logo found at', result.bestCandidate.centerX, result.bestCandidate.centerY);
}
```

---

#### `waitForImage()`

```typescript
vision.waitForImage(
  page: Page,
  templatePath: string,
  options?: VisionOptions
): Promise<MatchResult>
```

Polls until the template is found or the timeout expires. Stops immediately on terminal reasons (`invalid-template`, `invalid-region`, etc.) without burning the timeout.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `page` | `Page` | Playwright page instance |
| `templatePath` | `string` | Path to the template PNG file |
| `options` | `VisionOptions` | Optional. Uses `timeoutMs` (default: 1200ms) and `pollMs` (default: 100ms) |

**Returns:** `Promise<MatchResult>` -- Resolves with `found: true` on success.

**Throws:** On timeout, on terminal failure reasons, or when `BROWSER=lightpanda`.

```typescript
const result = await vision.waitForImage(page, 'assets/dialog.png', {
  region: 'main',
  timeoutMs: 5000,
});
```

---

#### `existsByImage()`

```typescript
vision.existsByImage(
  page: Page,
  templatePath: string,
  options?: VisionOptions
): Promise<boolean>
```

Boolean convenience wrapper around `locateByImage`. Returns `true` if found, `false` if `not-found`. Throws on `ambiguous`, terminal reasons, or Lightpanda.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `page` | `Page` | Playwright page instance |
| `templatePath` | `string` | Path to the template PNG file |
| `options` | `VisionOptions` | Optional matching configuration |

**Returns:** `Promise<boolean>`

**Throws:** On `ambiguous`, any terminal reason, or when `BROWSER=lightpanda`.

```typescript
const hasLogo = await vision.existsByImage(page, 'assets/logo.png', { region: 'header' });
expect(hasLogo).toBe(true);
```

---

#### `clickByImage()`

```typescript
vision.clickByImage(
  page: Page,
  templatePath: string,
  options?: VisionOptions
): Promise<ClickResult>
```

Waits for the template match (via `waitForImage`), highlights it, then clicks at the match center (or at the offset point if `clickOffset` is provided). Uses `page.mouse.click()`.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `page` | `Page` | Playwright page instance |
| `templatePath` | `string` | Path to the template PNG file |
| `options` | `VisionOptions` | Optional. `clickOffset` shifts click from match top-left |

**Returns:** `Promise<ClickResult>` -- Includes `clickPoint` with the actual click coordinates.

**Throws:** On timeout, terminal failure, or when `BROWSER=lightpanda`.

```typescript
await vision.clickByImage(page, 'assets/submit-btn.png', { region: 'main' });
```

---

#### `typeByImage()`

```typescript
vision.typeByImage(
  page: Page,
  templatePath: string,
  text: string,
  options?: VisionOptions
): Promise<ClickResult>
```

Clicks by image (via `clickByImage`), then types text using `page.keyboard.type()`. This is **keystroke simulation** -- each character is typed individually, triggering `keydown`/`keypress`/`keyup` events. This differs from `fill()` which sets the value directly.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `page` | `Page` | Playwright page instance |
| `templatePath` | `string` | Path to the template PNG file |
| `text` | `string` | Text to type after clicking |
| `options` | `VisionOptions` | Optional. `clickOffset` shifts where the click lands |

**Returns:** `Promise<ClickResult>` -- The click result from the underlying `clickByImage` call.

**Throws:** On timeout, terminal failure, or when `BROWSER=lightpanda`.

**Important:** `typeByImage` uses `page.keyboard.type()` (keystroke simulation), not `fill()` (direct value set). For direct value setting, use `typeByImageOr` which falls back to `fillFirstVisible` using `fill()`.

```typescript
await vision.typeByImage(page, 'assets/name-field.png', 'Alice', {
  region: 'main',
  clickOffset: { x: 300, y: 21 },
});
```

---

### Hybrid Functions (Vision + DOM Fallback)

---

#### `clickByImageOr()`

```typescript
vision.clickByImageOr(
  page: Page,
  templatePath: string,
  candidates: Locator[],
  options?: VisionOptions
): Promise<StrategyResult>
```

Tries vision first (`clickByImage`). If vision fails, clicks the first visible Locator from `candidates[]` (via `clickFirstVisible`). On Lightpanda (no screenshots), skips vision entirely and goes directly to DOM fallback.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `page` | `Page` | Playwright page instance |
| `templatePath` | `string` | Path to the template PNG file |
| `candidates` | `Locator[]` | Playwright Locator objects for DOM fallback |
| `options` | `VisionOptions` | Optional matching configuration |

**Returns:** `Promise<StrategyResult>` -- `{strategy: 'vision', result}` or `{strategy: 'dom'}`.

**Throws:** Only if both vision and DOM fallback fail (no visible candidate).

**Important:** `candidates` are **Playwright Locator objects**, not CSS selector strings. Compare with `typeByImageOr` which takes CSS selector strings.

```typescript
const result = await vision.clickByImageOr(
  page,
  'assets/login-btn.png',
  [page.locator('#login'), page.locator('button[type="submit"]')],
  { region: 'main' },
);
```

---

#### `typeByImageOr()`

```typescript
vision.typeByImageOr(
  page: Page,
  templatePath: string,
  text: string,
  selectors: string[],
  options?: VisionOptions
): Promise<StrategyResult>
```

Tries vision first (`typeByImage`). If vision fails, fills the first visible selector from `selectors[]` using `fillFirstVisible` (which uses Playwright's `fill()` method). On Lightpanda, skips vision and goes directly to DOM fallback.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `page` | `Page` | Playwright page instance |
| `templatePath` | `string` | Path to the template PNG file |
| `text` | `string` | Text to type (vision) or fill (DOM fallback) |
| `selectors` | `string[]` | CSS selector strings for DOM fallback |
| `options` | `VisionOptions` | Optional matching configuration |

**Returns:** `Promise<StrategyResult>` -- `{strategy: 'vision', result}` or `{strategy: 'dom'}`.

**Throws:** Only if both vision and DOM fallback fail (no visible selector).

**Important:** `selectors` are **CSS selector strings** (not Locator objects). The function creates locators internally via `page.locator()`. Compare with `clickByImageOr` which takes Locator objects.

**Important:** When vision succeeds, text is typed via `page.keyboard.type()` (keystroke simulation). When DOM fallback is used, text is set via `fill()` (direct value set). These have different behaviors for input events.

```typescript
await vision.typeByImageOr(
  page,
  'assets/name-row.png',
  'Alice',
  ['#name-input', 'input[name="name"]'],
  { region: 'main', clickOffset: { x: 300, y: 21 } },
);
```

---

### DOM Helper Functions

---

#### `highlightLocator()`

```typescript
vision.highlightLocator(
  locator: Locator,
  options?: VisionOptions
): Promise<{ strategy: 'dom' }>
```

Draws a temporary highlight overlay (Sakuli-style yellow border) around a Playwright Locator's bounding box. Uses the first matching element.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `locator` | `Locator` | Playwright Locator to highlight |
| `options` | `VisionOptions` | Optional. `highlightMs`, `highlightColor`, `highlightFillColor` |

**Returns:** `Promise<{ strategy: 'dom' }>`

**Throws:** If the locator is not visible or its bounding box cannot be determined.

```typescript
const btn = page.locator('#submit');
await vision.highlightLocator(btn, { highlightMs: 1000 });
```

---

#### `highlightFirstVisible()`

```typescript
vision.highlightFirstVisible(
  candidates: Locator[],
  options?: VisionOptions
): Promise<{ strategy: 'dom' }>
```

Highlights the first visible Locator from a candidate list. Iterates through `candidates` and highlights the first one that is visible.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `candidates` | `Locator[]` | List of Playwright Locators to try |
| `options` | `VisionOptions` | Optional highlight configuration |

**Returns:** `Promise<{ strategy: 'dom' }>`

**Throws:** If no candidate in the list is visible.

```typescript
await vision.highlightFirstVisible([
  page.locator('#primary-btn'),
  page.locator('.fallback-btn'),
]);
```

---

#### `highlightByImage()`

```typescript
vision.highlightByImage(
  page: Page,
  templatePath: string,
  options?: VisionOptions
): Promise<MatchResult>
```

Waits for an image match (via `waitForImage`) and highlights it without clicking. Useful for visual verification in demos and test recordings.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `page` | `Page` | Playwright page instance |
| `templatePath` | `string` | Path to the template PNG file |
| `options` | `VisionOptions` | Optional matching configuration |

**Returns:** `Promise<MatchResult>` -- The match result from `waitForImage`.

**Throws:** On timeout, terminal failure, or when `BROWSER=lightpanda`.

```typescript
await vision.highlightByImage(page, 'assets/logo.png', { region: 'header' });
```

---

#### `clickFirstVisible()`

```typescript
vision.clickFirstVisible(
  candidates: Locator[]
): Promise<{ strategy: 'dom' }>
```

Clicks the first visible Locator from a list. Highlights the target before clicking. The type declaration does not include an `options` parameter, but the implementation accepts an optional options object for highlight configuration.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `candidates` | `Locator[]` | List of Playwright Locators to try |

**Returns:** `Promise<{ strategy: 'dom' }>`

**Throws:** If no candidate in the list is visible (`'No visible click target found.'`).

```typescript
await vision.clickFirstVisible([
  page.locator('#save-btn'),
  page.locator('button:has-text("Save")'),
]);
```

---

#### `fillFirstVisible()`

```typescript
vision.fillFirstVisible(
  page: Page,
  selectors: string[],
  value: string,
  options?: VisionOptions
): Promise<{ strategy: 'dom' }>
```

Fills the first visible selector from a list of CSS selector strings. Creates Locators internally via `page.locator()`. Highlights the target before filling. Uses Playwright's `fill()` method (direct value set).

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `page` | `Page` | Playwright page instance |
| `selectors` | `string[]` | CSS selector strings (not Locator objects) |
| `value` | `string` | Value to fill into the input |
| `options` | `VisionOptions` | Optional highlight configuration |

**Returns:** `Promise<{ strategy: 'dom' }>`

**Throws:** If no selector in the list resolves to a visible element (`'No visible selector found for value ...'`).

**Important:** Takes CSS selector **strings**, not Locator objects. The function calls `page.locator(selector).first()` internally.

```typescript
await vision.fillFirstVisible(page, ['#email', 'input[type="email"]'], 'user@example.com');
```

---

#### `clickBestEffort()`

```typescript
vision.clickBestEffort(
  locator: Locator,
  options?: VisionOptions
): Promise<{ strategy: 'dom' }>
```

Progressive click fallback chain: standard click, then forced click (`{ force: true }`), then DOM `evaluate` click (`el.click()`). Scrolls into view first (unless `scrollIntoView: false`). Highlights if `highlightMs` is set or `CEP_VISION_HIGHLIGHT_MS` env is set.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `locator` | `Locator` | Playwright Locator to click |
| `options` | `VisionOptions` | Optional. `scrollIntoView`, `highlightMs` |

**Returns:** `Promise<{ strategy: 'dom' }>`

**Throws:** If all three click strategies fail (`'clickBestEffort: all click strategies failed'`).

```typescript
const tricky = page.locator('.overlapped-button');
await vision.clickBestEffort(tricky);
```

---

#### `typeBestEffort()`

```typescript
vision.typeBestEffort(
  locator: Locator,
  text: string,
  options?: VisionOptions
): Promise<{ strategy: 'dom' }>
```

Progressive type fallback chain: click + `type()`, then forced click + `type()`, then DOM `evaluate` (focus + set `value` + dispatch `input` event). Scrolls into view first.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `locator` | `Locator` | Playwright Locator to type into |
| `text` | `string` | Text to type |
| `options` | `VisionOptions` | Optional. `scrollIntoView`, `highlightMs` |

**Returns:** `Promise<{ strategy: 'dom' }>`

**Throws:** If all three type strategies fail (`'typeBestEffort: all type strategies failed'`).

```typescript
const input = page.locator('#search');
await vision.typeBestEffort(input, 'hello world');
```

---

#### `fillBestEffort()`

```typescript
vision.fillBestEffort(
  locator: Locator,
  value: string,
  options?: VisionOptions
): Promise<{ strategy: 'dom' }>
```

Progressive fill fallback chain: `fill()`, then click + `fill()`, then DOM `evaluate` (focus + set `value` + dispatch `input` and `change` events). Scrolls into view first.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `locator` | `Locator` | Playwright Locator to fill |
| `value` | `string` | Value to set |
| `options` | `VisionOptions` | Optional. `scrollIntoView`, `highlightMs` |

**Returns:** `Promise<{ strategy: 'dom' }>`

**Throws:** If all three fill strategies fail (`'fillBestEffort: all fill strategies failed'`).

```typescript
const input = page.locator('#username');
await vision.fillBestEffort(input, 'admin');
```

---

## Constants

```typescript
vision.constants.DEFAULT_CONFIDENCE      // 0.9
vision.constants.DEFAULT_TIMEOUT_MS      // 1200
vision.constants.DEFAULT_POLL_MS         // 100
vision.constants.DEFAULT_AMBIGUITY_GAP   // 0.03
vision.constants.DEFAULT_SCALES          // [0.97, 1.0, 1.03]
vision.constants.DEFAULT_SCORE_WEIGHTS   // { gray: 0.45, color: 0.55 }
```

| Constant | Value | Used by |
|----------|-------|---------|
| `DEFAULT_CONFIDENCE` | `0.9` | Minimum `combinedScore` to accept a match |
| `DEFAULT_TIMEOUT_MS` | `1200` | Polling timeout for `waitForImage` and functions that use it |
| `DEFAULT_POLL_MS` | `100` | Polling interval between locate attempts |
| `DEFAULT_AMBIGUITY_GAP` | `0.03` | Minimum score gap between best and second candidate |
| `DEFAULT_SCALES` | `[0.97, 1.0, 1.03]` | Scale variants tried during template matching |
| `DEFAULT_SCORE_WEIGHTS` | `{ gray: 0.45, color: 0.55 }` | Weighting for `combinedScore = 0.45*gray + 0.55*color` |

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CEP_VISION_HIGHLIGHT_MS` | `700` | Global highlight duration in milliseconds. Set to `0` to disable highlighting. |
| `CEP_VISION_DEBUG` | unset | When `1`, enables debug artifact writing. |
| `BROWSER` | `chromium` | When `lightpanda`, all vision functions throw or fall back to DOM. |

---

## Debug Artifacts

When `debugDir` and `debugLabel` are set in options (or `CEP_VISION_DEBUG=1`), the following files are written:

| File | Content |
|------|---------|
| `{label}-region.png` | The cropped screenshot of the search region |
| `{label}-annotated.png` | The region screenshot with match rectangles drawn on it |
| `{label}-meta.json` | Full `MatchResult` as JSON for programmatic inspection |

---

## Important Notes

- **All vision functions throw** if `BROWSER=lightpanda` (no visual rendering). Use `canScreenshot()` to check, or use hybrid functions (`clickByImageOr`, `typeByImageOr`) which fall back to DOM automatically.
- **`typeByImage`** uses `page.keyboard.type()` (keystroke simulation -- individual key events). **`typeByImageOr` DOM fallback** uses `fill()` (direct value set -- no key events). These have different behaviors for autocomplete, input masks, and event listeners.
- **`clickByImageOr`** takes **Locator objects** as `candidates`. **`typeByImageOr`** takes **CSS selector strings** as `selectors`. **`fillFirstVisible`** also takes CSS selector strings and creates locators internally.
- **Click offset behavior:** Without `clickOffset`, clicks land at `match.centerX`, `match.centerY`. With `clickOffset`, clicks land at `match.x + offset.x`, `match.y + offset.y` (offset from the match top-left corner).
- **Terminal reasons** (`invalid-template`, `invalid-region`, `invalid-options`, `invalid-size`, `scoring-failed`, `unreadable-template`) cause immediate failure in `waitForImage` without retrying. Non-terminal reasons (`not-found`, `ambiguous`) are retried until timeout.
