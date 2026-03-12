# Writing Tests for check_cep

This handbook covers check_cep-specific topics for test authors:
folder conventions, the `check-cep-vision` visual matching API,
persistent template images, regions, click offsets, and choosing
between DOM and vision selectors.

**Prerequisite**: You have completed the [TUTORIAL.md](TUTORIAL.md) setup
(container image built, first test passing).  This handbook picks up
where the tutorial leaves off.

**Audience**: Test writers authoring Playwright test suites that run
inside check_cep's Podman container.  For general Playwright usage,
refer to the [Playwright documentation](https://playwright.dev/docs/intro).

---

## Folder Structure

Every test suite lives under a directory that the container mounts at
`/home/pwuser/tests`.  Two layouts are valid:

### Pattern A: Nested Enterprise Layout

Shared helpers at the suite root, test cases in subdirectories:

```
tests/
  functions/          # Shared utility modules
    gateway-helper.ts
    index.ts
  variables/          # Shared config, secrets
    account.ts
    index.ts
  EXT/E2E_MON_Checks/Supermarket/YBIYRI/etl/prod/
    be.test.ts
    playwright.config.ts
```

### Pattern B: Flat Per-Case Layout

Each test case is self-contained with its own subdirectories:

```
tests/
  MyTestCase/
    assets/               # Template PNGs for vision matching
      login-btn.png
    functions/            # Case-specific helpers (or empty)
    variables/
      index.ts            # Test data
    pages/                # Local HTML fixtures (if applicable)
      form.html
    playwright.config.ts  # Render baseline config
    MyTestCase.test.ts    # Test entry point
    capture-templates.mjs # Standalone script to regenerate assets/
    README.md             # Inline guidance
```

### Discovery Rules

The container's `run.py` walks the test directory looking for
`*.test.ts` (or `*.test.js`) files.  It **skips** three directory names:

- `functions` — shared utility modules
- `variables` — configuration and test data
- `node_modules` — npm packages

Everything else is traversed.  The `assets/` and `pages/` directories
are not skipped but contain no test files, so they are ignored by
discovery.

---

## check-cep-vision API

The `check-cep-vision` library provides image-based visual matching
for Playwright tests.  It is bundled in the container at
`/home/pwuser/node_modules/check-cep-vision`.

### Import

```typescript
import { vision } from 'check-cep-vision';
```

### Function Reference

#### Vision-Only (image-based interaction)

| Function | Description |
|----------|-------------|
| `vision.locateByImage(page, templatePath, options?)` | Locate a template on the page.  Returns `MatchResult`. |
| `vision.waitForImage(page, templatePath, options?)` | Poll until the template is found.  Returns `MatchResult`. |
| `vision.existsByImage(page, templatePath, options?)` | Check if a template exists.  Returns `boolean`. |
| `vision.clickByImage(page, templatePath, options?)` | Find and click a template.  Returns `ClickResult`. |
| `vision.typeByImage(page, templatePath, text, options?)` | Find, click, and type text.  Returns `ClickResult`. |

#### DOM Helpers (Playwright locator convenience)

| Function | Description |
|----------|-------------|
| `vision.clickFirstVisible(candidates)` | Click the first visible Playwright locator from the list. |
| `vision.fillFirstVisible(page, selectors, value, options?)` | Fill the first visible CSS selector from the list. |

Note: `clickFirstVisible` takes **Playwright locators** while
`fillFirstVisible` takes **CSS selector strings**.

#### Hybrid (vision-first with DOM fallback)

| Function | Description |
|----------|-------------|
| `vision.clickByImageOr(page, templatePath, candidates, options?)` | Try vision; fall back to `clickFirstVisible(candidates)`. Returns `StrategyResult`. |
| `vision.typeByImageOr(page, templatePath, text, selectors, options?)` | Try vision; fall back to `fillFirstVisible(page, selectors, text)`. Returns `StrategyResult`. |

Note: `clickByImageOr` takes **Playwright locators** for its fallback,
while `typeByImageOr` takes **CSS selector strings**.

#### Debug (visual feedback)

| Function | Description |
|----------|-------------|
| `vision.highlightByImage(page, templatePath, options?)` | Locate and highlight an image match without clicking. |
| `vision.highlightLocator(locator, options?)` | Draw a highlight overlay around a Playwright locator. |
| `vision.highlightFirstVisible(candidates, options?)` | Highlight the first visible locator from a list. |

### VisionOptions

```typescript
interface VisionOptions {
  region?: RegionPreset | RectRegion;  // Constrain search area
  confidence?: number;                  // Min score (default: 0.9)
  ambiguityGap?: number;               // Min gap between top matches (default: 0.03)
  timeoutMs?: number;                   // Poll timeout (default: 1200)
  pollMs?: number;                      // Poll interval (default: 100)
  clickOffset?: { x: number; y: number }; // Offset from match top-left
  debugDir?: string;                    // Write debug artifacts to this directory
  debugLabel?: string;                  // Label for debug artifacts
  scales?: number[];                    // Template scale factors (default: [0.97, 1.0, 1.03])
  fullPage?: boolean;                   // Screenshot full page (default: false)
  maxCandidates?: number;               // Max candidates to evaluate
  highlightMs?: number;                 // Highlight duration in ms
  highlightColor?: string;              // Highlight overlay color
}
```

### Return Types

- **`MatchResult`**: `{ found, reason, confidence, bestCandidate, secondCandidate, ... }`
- **`ClickResult`**: extends `MatchResult` with `{ clickPoint: { x, y } }`
- **`StrategyResult`**: `{ strategy: 'vision' | 'dom', result?: ClickResult }`

### Constants

Access defaults via `vision.constants`:

```typescript
vision.constants.DEFAULT_CONFIDENCE    // 0.9
vision.constants.DEFAULT_TIMEOUT_MS    // 1200
vision.constants.DEFAULT_POLL_MS       // 100
vision.constants.DEFAULT_AMBIGUITY_GAP // 0.03
vision.constants.DEFAULT_SCALES        // [0.97, 1.0, 1.03]
vision.constants.DEFAULT_SCORE_WEIGHTS // { gray: 0.45, color: 0.55 }
```

---

## Persistent Template Images

Template images are pre-captured PNGs stored in `assets/` and committed
to version control.  They serve as the visual "selectors" for
`check-cep-vision`.

### Creating Templates

Write a standalone `.mjs` capture script (not a Playwright test) that
opens the target page at the render baseline and screenshots each
interactive element:

```javascript
// capture-templates.mjs — run with: node capture-templates.mjs
import { chromium } from 'playwright';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const assetDir = path.join(__dirname, 'assets');
const pageUrl = 'file://' + path.join(__dirname, 'pages/form.html');

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
});
await page.goto(pageUrl);
await page.evaluate(() => document.fonts.ready);

await page.locator('#row-name').screenshot({
  path: path.join(assetDir, 'name-row.png'),
  animations: 'disabled',
});
await browser.close();
```

Run this inside the container to ensure container fonts are used:

```bash
podman run --rm \
  --volume ./tests/fixtures/MyTestCase:/home/pwuser/tests:rw,z \
  check_cep:test \
  node /home/pwuser/tests/capture-templates.mjs
```

### The `functions/` Helper Pattern

Each fixture exports shared utilities from `functions/index.ts`:

```typescript
// functions/index.ts
import * as path from 'node:path';

export const asset = (name: string) => path.resolve(`assets/${name}`);
export const FORM_URL = 'file://' + path.resolve('pages/form.html');
export const INPUT_OFFSET = { x: 300, y: 21 };
```

Test files import from `./functions`:

```typescript
import { asset, FORM_URL, INPUT_OFFSET } from './functions';

await vision.clickByImage(page, asset('submit-btn.png'), { region: 'main' });
```

The `functions/` directory is excluded from run.py's test discovery, so
helpers there never run as test files.

### Render Baseline

All templates must be captured under the same render baseline:

| Setting | Value |
|---------|-------|
| Viewport | 1280 x 720 |
| deviceScaleFactor | 1 |
| Fonts | Container defaults (Arial, sans-serif) |
| Animations | Disabled |

### Why Commit Templates

Persistent templates ensure reproducibility.  Unlike the synthetic test
fixtures (which capture templates dynamically at test time), example
fixtures commit their templates so that:

1. The test is deterministic across runs
2. Template quality can be reviewed in PRs
3. No runtime capture overhead

---

## Template Best Practices

### What Makes a Good Template

- **Include labels when they disambiguate**: A bare text input looks
  identical to every other bare text input.  Capturing the full field
  row (label + input together) makes each template visually unique.

- **Use field-row templates, not bare inputs**: `#row-name` (label +
  input) is better than `#name-input` (just the input).

- **Avoid too much background**: Templates with large areas of page
  background may match at multiple locations.  Keep templates tight
  around the target element.

- **Capture interactive elements in their default state**: Empty inputs,
  unhovered buttons, unchecked checkboxes.

### Common Pitfalls

- **Wrong scale**: If templates were captured at a different
  `deviceScaleFactor`, matching will fail or score poorly.  Always use
  `deviceScaleFactor: 1`.

- **Non-container fonts**: Capturing on the host with different fonts
  produces templates that don't match inside the container.  Always
  capture inside the container.

- **Too-generic templates**: A plain gray rectangle will match
  everywhere.  Include distinguishing text or icons.

- **Placeholder text in inputs**: If you capture a template with
  placeholder text visible, it won't match when the field is filled (or
  vice versa).  Capture in the state your test expects to find.

### Verifying Template Quality

View the PNGs in your file manager or image viewer.  Each template
should clearly show the target element with enough context to be
unique on the page.  Run the test — if vision matching succeeds,
the template is good.

---

## Regions and Click Offsets

### Region Presets

Named presets divide the viewport into logical areas:

| Preset | Area |
|--------|------|
| `'header'` | Top strip of the viewport |
| `'main'` | Center area |
| `'footer'` | Bottom strip |
| `'left'` | Left half |
| `'right'` | Right half |
| `'topLeft'` | Top-left quadrant |
| `'topRight'` | Top-right quadrant |

### Explicit RectRegion

For precise control, pass pixel coordinates:

```typescript
const RIGHT_PANEL = { x: 740, y: 230, width: 530, height: 65 };

await vision.clickByImage(page, asset('delete-btn.png'), {
  region: RIGHT_PANEL,
});
```

Derive coordinates from the element's bounding box at the render
baseline (1280x720).  Add a small margin (5-10 px) for robustness.

### When to Use Regions

- **Always on busy pages**: Multiple similar elements trigger ambiguity
  rejection.  Regions narrow the search to the intended area.
- **For speed**: Smaller search areas are faster to scan.
- **As a best practice**: Even on simple pages, `region: 'main'`
  documents intent and avoids accidental matches in headers/footers.

### Click Offsets

By default, `clickByImage` and `typeByImage` click the center of the
matched bounding box.  When the template includes a label alongside the
input, the center falls on the label — not where you want to type.

Use `clickOffset` to shift the click point:

```typescript
// Field-row template is 424×42 px.  Label takes ~110 px on the left.
// Offset { x: 300, y: 21 } places the click in the input area.
await vision.typeByImage(page, asset('name-row.png'), 'Alice', {
  region: 'main',
  clickOffset: { x: 300, y: 21 },
});
```

The offset is relative to the **top-left corner** of the match bounding
box.  Without an offset, the click lands at the center.

---

## Selector Strategy Guide

### When to Use DOM Selectors

- The page has stable `id` attributes or `data-testid` markers
- You don't need to verify visual appearance
- Speed matters (DOM selectors are faster than vision matching)

```typescript
await page.locator('#name-input').fill('Alice');
await page.locator('#submit-btn').click();
```

### When to Use Vision Selectors

- The DOM structure is unstable or generated dynamically
- You need to verify that elements are visually present and correct
- You're migrating from Sakuli (which was image-based)
- The page lacks stable selectors

```typescript
await vision.typeByImage(page, asset('name-row.png'), 'Alice', {
  region: 'main',
  clickOffset: { x: 300, y: 21 },
});
```

### When to Use Hybrid Selectors (Recommended for Production)

The hybrid approach tries vision first and falls back to DOM selectors
if vision matching fails.  This gives you:

- Visual verification when possible
- Reliability even if rendering changes slightly

```typescript
// typeByImageOr: vision first, CSS selector fallback
await vision.typeByImageOr(
  page,
  asset('name-row.png'),
  'Alice',
  ['#name-input', 'input[name="name"]'],  // CSS selector strings
  { region: 'main', clickOffset: { x: 300, y: 21 } },
);

// clickByImageOr: vision first, Playwright locator fallback
await vision.clickByImageOr(
  page,
  asset('submit-btn.png'),
  [page.locator('#submit-btn')],  // Playwright locators
  { region: 'main' },
);
```

### Checking Which Strategy Was Used

Hybrid methods return a `StrategyResult`:

```typescript
const result = await vision.typeByImageOr(page, template, text, selectors);
console.log(result.strategy);  // 'vision' or 'dom'
```

The form fixture (`tc_vision_example_form`) demonstrates all three
strategies side by side on the same page with the same assertions.

---

## Running and Debugging Tests

### How Tests Execute

```
check_cep (host) → Podman container → run.py → npx playwright test
```

The host-side `check_cep` plugin copies your test directory into the
container, `run.py` discovers `*.test.ts` files, and Playwright runs
them.  Results are written to the results directory.

### Quick Local Run

```bash
make test-local
```

Or run a specific fixture:

```bash
pytest tests/integration/test_modes.py -k "tc_vision_example_form and local" -v
```

### Interactive Development

Use `--headed --shell` for live debugging.  See [TUTORIAL.md, section 8](TUTORIAL.md)
for headed mode setup and usage.

### Spectate Mode

Run the integration tests with a visible browser on your desktop.  The
browser slows down so a human spectator can follow the actions:

```bash
CEP_SPECTATE=1 pytest tests/integration/test_modes.py -k "vision_example and local" -v
```

Spectate mode injects `--headed`, enables `CEP_SLOW_MO` (default 400 ms
between each browser action), and sets `CEP_VISION_HIGHLIGHT_MS`
(default 2000 ms highlight overlay on vision matches).  Timeouts are
automatically bumped so slow actions don't cause failures.

Tune the speed with environment variables:

| Variable | Default | Effect |
|----------|---------|--------|
| `CEP_SPECTATE` | (unset) | Enable spectate mode when set to any non-empty value |
| `CEP_SLOW_MO` | `400` | Milliseconds delay before each browser action |
| `CEP_VISION_HIGHLIGHT_MS` | `2000` | Duration of the vision match highlight overlay |

Example — faster pace:

```bash
CEP_SPECTATE=1 CEP_SLOW_MO=150 CEP_VISION_HIGHLIGHT_MS=800 \
  pytest tests/integration/test_modes.py -k "vision_example and local" -v
```

### Debug Artifacts

Pass `debugDir` to write diagnostic files for each vision operation:

```typescript
await vision.clickByImage(page, asset('btn.png'), {
  region: 'main',
  debugDir: '/home/pwuser/results/debug',
  debugLabel: 'submit-click',
});
```

This writes to the debug directory:

| File | Contents |
|------|----------|
| `*-region.png` | The search region cropped from the screenshot |
| `*-annotated.png` | The screenshot with match boxes drawn |
| `*-meta.json` | Match scores, candidate positions, configuration |

Use these to diagnose why a match failed:
- Low score → template may not match the current rendering
- Ambiguity → multiple candidates with close scores (narrow the region)
- No candidates → template not visible in the search area

---

## Visual Narration for Headed Demos

When running tests in headed mode (visible browser), you may want visual
highlighting to narrate what the test is doing. This is useful for:
- Demo presentations
- Debugging alongside a human spectator
- Recording test execution videos

### The Pattern: Playwright Finds, CEP Highlights

Use Playwright's robust locators to find elements, then use
`vision.highlightLocator()` to draw a visible overlay:

```typescript
// 1. Playwright finds the element (auto-waits, stable)
await expect(page.getByRole('heading', { name: /Welcome/i })).toBeVisible();

// 2. CEP highlights it for human spectators
await vision.highlightLocator(page.getByRole('heading', { name: /Welcome/i }));
```

### Why vision.highlightLocator() Instead of Playwright's .highlight()?

Playwright 1.58+ has a built-in `.highlight()` method on locators, but
`vision.highlightLocator()` is preferred for demos because:

| Feature | Playwright `.highlight()` | `vision.highlightLocator()` |
|--------|--------------------------|----------------------------|
| Duration | ~2 seconds (brief) | Configurable (default 2.2s via `CEP_VISION_HIGHLIGHT_MS`) |
| Colors | Default only | Customizable (`highlightColor`, `highlightFillColor`) |
| Use case | Quick debugging | Demo/visual narration |

### Customizing Highlights

Pass options to customize highlight appearance:

```typescript
await vision.highlightLocator(page.getByRole('link', { name: /Submit/i }), {
  highlightMs: 1500,              // Duration in ms
  highlightColor: '#ff0000',       // Border color
  highlightFillColor: 'rgba(255, 0, 0, 0.1)', // Fill color
});
```

### Environment Variables

Control highlight duration globally:

```bash
# Set highlight to 3 seconds
CEP_VISION_HIGHLIGHT_MS=3000 python3 src/check_cep ...
```

### Anti-Pattern: Convenience Helpers That Skip Auto-Waiting

Avoid helpers that bypass Playwright's built-in auto-waiting:

```typescript
// BAD: clickFirstVisible doesn't auto-wait for elements
await vision.clickFirstVisible([locator1, locator2]);  // May fail intermittently

// GOOD: Pure Playwright click auto-waits for visibility + stability
await page.getByRole('button', { name: /Submit/i }).click();
```

The `vision.clickFirstVisible()` and `vision.highlightFirstVisible()`
convenience helpers are useful for migration from Sakuli, but they don't
have Playwright's auto-waiting behavior. For stable tests, prefer
pure Playwright locators.

---

## Worked Examples

Three example fixtures demonstrate different aspects of the vision API.
Each includes a README.md with detailed guidance.

### tc_vision_example_form

**Path**: `tests/fixtures/tc_vision_example_form/`

Multi-field contact form with three test strategies side by side (vision,
DOM, hybrid).  Demonstrates persistent field-row templates, click
offsets for label+input rows, and the `functions/` helper pattern
(`asset()`, `FORM_URL`, `INPUT_OFFSET`, `assertFormFilled()`).
Best starting point for understanding the three selector approaches.

See [tc_vision_example_form/README.md](tests/fixtures/tc_vision_example_form/README.md).

### tc_vision_example_console

**Path**: `tests/fixtures/tc_vision_example_console/`

Dense admin dashboard with six identical "Delete job" buttons.
Demonstrates ambiguity rejection on a broad search and region-guided
resolution by narrowing to a specific row.  The region-scoped test
includes `debugDir` / `debugLabel` to write diagnostic artifacts.
Best example for understanding `RectRegion` and debug output.

See [tc_vision_example_console/README.md](tests/fixtures/tc_vision_example_console/README.md).

### tc_vision_example_login

**Path**: `tests/fixtures/tc_vision_example_login/`

Realistic login flow on a visually busy page with navbar, hero banner,
feature cards, social login buttons, and the primary CTA.  Two tests:
vision-only (with `debugDir` on the username field) and hybrid
(`typeByImageOr` / `clickByImageOr`).  Demonstrates that template
design (CTA is visually distinct from social buttons) eliminates
ambiguity without explicit regions.

See [tc_vision_example_login/README.md](tests/fixtures/tc_vision_example_login/README.md).
