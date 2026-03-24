# Writing Tests for check_cep

This handbook covers check_cep-specific topics for test authors:
folder conventions, the `check-cep-vision` visual matching API,
persistent template images, regions, click offsets, and choosing
between DOM and vision selectors.

**Prerequisite**: You have completed the [README.md](README.md) setup
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

> **Early stage — use with a grain of salt.**  The vision matching
> library works well in our integration tests and first customer
> deployments, but it is not yet battle-hardened.  Some pages or
> layouts may produce unreliable matches.  If vision matching does not
> work for your use case, don't fight it — use standard Playwright
> DOM locators instead, or use the hybrid functions (`clickByImageOr`,
> `typeByImageOr`) which fall back to DOM selectors automatically.
> We will not investigate individual vision matching failures at this
> point.

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

## Advanced Tips for Tricky Realistic Fixtures

The strongest recent fixtures in this repository are not "clean demo pages"
but intentionally crowded, repetitive, realistic-looking layouts.  This is
where `check-cep-vision` becomes genuinely useful: not because it can solve
arbitrary chaos, but because it can handle **hard-but-fair** visual problems
when the fixture author designs the page and the test together.

### The Right Goal

When you write a tricky local fixture, do **not** aim for magical success on a
messy page.  Aim for this pattern instead:

1. A broad search is **supposed** to be ambiguous or unsafe.
2. The test proves that ambiguity explicitly.
3. The test applies a guided strategy such as narrowing the region or using an
   anchor image first.
4. The correct target is found.
5. The page state proves that the right element changed and the wrong similar
   element did not.

This is much more valuable than a toy page where every visual target is unique.

### Good Realistic Stressors

Use these on local deterministic fixtures:

- repeated cards with near-identical controls,
- multiple visually similar product or article previews,
- colorful promo chips and layout noise,
- mixed categories that make the page feel real,
- sticky sidebars or dense content blocks,
- small crops that are intentionally too weak for full-page search.

Avoid these in the green-path regression lane:

- uncontrolled live websites,
- randomized ads,
- arbitrary animation drift,
- severe occlusion,
- personalization,
- scenarios that would require OCR or redesign tolerance.

### Pattern 1: Assert Ambiguity First

On crowded pages, a broad search should often be tested like this:

```typescript
const result = await vision.locateByImage(page, asset('preview.png'), {
  fullPage: true,
  confidence: 0.55,
});

expect(result.found).toBe(false);
expect(result.reason).toContain('ambig');
```

This is not a failure of the fixture.  It is the point of the fixture.

### Pattern 2: Tighten the Region Repeatedly

The most reliable success path on realistic pages is usually:

- broad search to learn that the template is ambiguous,
- narrow to the target card,
- if still too broad, narrow again to the exact preview or sub-panel,
- then click inside that small region.

Example:

```typescript
const previewBox = await page.locator(TARGET_TILE_ID + ' .preview').boundingBox();

const targetRegion = {
  x: Math.floor(previewBox!.x - 8),
  y: Math.floor(previewBox!.y - 8),
  width: Math.ceil(previewBox!.width + 16),
  height: Math.ceil(previewBox!.height + 16),
};

await vision.clickByImage(page, asset('dryer-ambiguous-crop.png'), {
  region: targetRegion,
  confidence: 0.56,
  ambiguityGap: 0.05,
  clickOffset: { x: 30, y: 30 },
});
```

Important lesson: sometimes the target **card** is still too broad.  The right
region is the exact **preview box** plus a small padding margin.

### Pattern 3: Use a Unique Anchor First, Then the Real Target

Sometimes the final target image is too weak to use globally, but a nearby
badge or label is unique.  In that case:

1. find the unique anchor globally,
2. derive a follow-up region from the anchor's `bestCandidate`,
3. search for the real target image only inside that region.

Example:

```typescript
const anchor = await vision.locateByImage(page, asset('night-sale-badge.png'), {
  fullPage: true,
  confidence: 0.9,
});

const candidate = anchor.bestCandidate!;
await page.evaluate((scrollY) => window.scrollTo(0, Math.max(0, scrollY)), candidate.y - 40);
await page.waitForTimeout(100);

const viewportAnchorY = await page.evaluate((pageY) => pageY - window.scrollY, candidate.y);
const stagedRegion = {
  x: Math.max(0, Math.floor(candidate.x - 20)),
  y: Math.max(0, Math.floor(viewportAnchorY - 10)),
  width: Math.ceil(candidate.width + 220),
  height: Math.ceil(candidate.height + 210),
};

await vision.clickByImage(page, asset('aurora-preview.png'), {
  region: stagedRegion,
  confidence: 0.83,
  clickOffset: { x: 48, y: 48 },
});
```

This staged pattern is ideal for realistic marketplaces, article cards, and
other repeated layouts where a single weak crop cannot safely identify the
correct item on its own.

### Similar Photos: What Actually Works

When two real photos are visually similar, the wrong instinct is to keep making
the template bigger until one item becomes unique.  That defeats the point of
the scenario.

What works better:

- crop a **smaller but still meaningful** region from the target photo,
- use that crop to prove full-page ambiguity,
- then scope the match to the intended card or preview region.

In other words: if the website really contains two similar products, let the
template stay weak enough to reflect that reality, and solve the problem with
guidance rather than with a deceptively over-specific crop.

### Tune With Evidence, Not Guessing

When a match behaves badly, inspect the raw result before changing the test:

- `result.reason`
- `result.bestCandidate?.combinedScore`
- `result.secondCandidate?.combinedScore`

Interpretation guide:

- `found` when you expected `ambiguous` -> template is too exact or too large
- `not-found` in a narrow region -> template is weak, confidence is too high,
  or the region is too tight
- `ambiguous` in a supposedly narrow region -> the region is still too broad

Do not tune blindly.  Use direct `locateByImage()` probes until the behavior is
understood.

### `fullPage` and `region` Cannot Be Combined

This is an easy mistake to make when refactoring a broad search into a guided
search.

Do **not** pass both:

- `fullPage: true`
- `region: {...}`

Use `fullPage: true` only for broad discovery.  Use `region` only for guided
matching.

### Be Careful with Coordinates After Scrolling

If a full-page match returns a `bestCandidate`, those coordinates are page
coordinates.  If you scroll and then derive a new region for a follow-up
operation, convert carefully.  A region that was correct before scrolling may be
wrong afterward if you treat page coordinates as viewport coordinates.

If the result becomes mysteriously `not-found` after scroll, inspect the region
math first.

### Use Debug Artifacts on Hard Matches

For realistic fixtures, add debug artifacts to the tricky calls:

```typescript
await vision.clickByImage(page, asset('preview.png'), {
  region: targetRegion,
  debugDir: '/home/pwuser/results/debug',
  debugLabel: 'preview-match',
});
```

This is especially useful when:

- you are tuning thresholds,
- you are checking whether the region clipped too much,
- you are debugging ambiguous matches,
- you are comparing two very similar photo-based targets.

### Assert Behavior, Not Only Match Success

Never stop at "the image matched."  On realistic pages, the wrong nearby item
may also be clickable.

Always assert the actual outcome, for example:

- `body` attribute changed to the intended item id,
- target tile gained `data-opened="true"`,
- target status text changed,
- distractor tile did **not** change,
- detail panel shows the correct title.

This is what turns a visual match into a trustworthy end-to-end test.

### Recommended Structure for a Hard Fixture

For realistic vision fixtures, this three-test pattern works well:

1. **Page-shape sanity test**
   - counts tiles, cards, promo chips, or repeated groups
2. **Broad ambiguity test**
   - proves the small crop is unsafe globally
3. **Guided success test**
   - narrows the search and proves the correct element changed state

That structure makes debugging much easier than a single giant test.

### Capture Templates Inside the Container

This matters even more for tricky pages than for simple ones.  Small rendering
differences are enough to turn a weak crop from "ambiguous" into "not-found" or
from "usable" into "too exact".  Always capture templates in the container with
the same viewport and DPR as the fixture tests.

### Worked Examples for These Patterns

- `tests/fixtures/tc_marketplace_preview_tile/` - broad ambiguity on a small
  preview crop, then region-guided success on a noisy synthetic marketplace
- `tests/fixtures/tc_marketplace_anchor_then_target/` - unique anchor first,
  then target-image matching inside an anchor-derived region
- `tests/fixtures/tc_marketplace_real_photo_pair/` - two similar real photos,
  a deliberately ambiguous crop, and preview-scoped recovery

---

## Selector Strategy Guide

### When to Use DOM Selectors (Default Choice)

DOM selectors are the **recommended default**.  They are fast, reliable,
and benefit from Playwright's built-in auto-waiting:

- The page has stable `id` attributes or `data-testid` markers
- You don't need to verify visual appearance
- Speed matters (DOM selectors are faster than vision matching)

```typescript
await page.locator('#name-input').fill('Alice');
await page.locator('#submit-btn').click();
```

### When to Use Vision Selectors (Experimental)

Vision-only selectors can work but are less predictable.  Consider them
only when DOM selectors are truly not an option:

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

### When to Use Hybrid Selectors (Recommended If You Want Vision)

If you want the visual verification that vision provides but cannot
afford flaky tests, **always use the hybrid functions**.  They try
vision first and fall back to DOM selectors automatically:

- Visual verification when it works, DOM reliability when it doesn't
- No test failures due to vision quirks — the fallback catches them

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

## Structuring Tests with `test.step()`

### Why Steps Matter

check_cep automatically extracts performance data from Playwright's
`steps.json` output.  When you group actions inside `test.step()`,
each step's duration becomes a separate Nagios performance metric.
This gives your monitoring system per-step timing data without any
extra code.

### Example

```typescript
import { test, expect } from '@playwright/test';

test('checkout flow', async ({ page }) => {
  await test.step('open product page', async () => {
    await page.goto('https://shop.example.com/product/42');
    await expect(page.getByRole('heading', { name: /Widget/ })).toBeVisible();
  });

  await test.step('add to cart', async () => {
    await page.getByRole('button', { name: 'Add to cart' }).click();
    await expect(page.getByText('Added')).toBeVisible();
  });

  await test.step('complete checkout', async () => {
    await page.getByRole('link', { name: 'Checkout' }).click();
    await page.getByLabel('Email').fill('test@example.com');
    await page.getByRole('button', { name: 'Pay' }).click();
    await expect(page.getByText('Thank you')).toBeVisible();
  });
});
```

### What You Get in Nagios

The above test produces performance data like:

```
'TestDuration'=4523ms 'OpenProductPage'=1200ms 'AddToCart'=823ms 'CompleteCheckout'=2500ms 'duration'=7s
```

Each `test.step()` title is converted to CamelCase and reported with
its duration in milliseconds.  The overall test duration and
wall-clock time are always included.

### Best Practices

- **Name steps after business actions**, not technical details:
  `'submit order'` rather than `'click button and wait for response'`.
- **Keep steps coarse-grained** — one step per logical user action.
  Too many fine-grained steps create noisy perfdata.
- **Steps can be nested** — inner steps appear as separate metrics too,
  so use nesting sparingly.
- **Step names become metric labels** — keep them short and stable.
  Renaming a step changes the metric name, which breaks dashboards.

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

Use `--headed --shell` for live debugging.  See [README.md, section 8](README.md)
for headed mode setup and usage.

### Recording Tests with Codegen

The fastest way to start a new test is to record your interactions.
Playwright's **codegen** tool watches what you do in the browser and
generates the corresponding test code in real time.

Inside a `--headed --shell` container session, run:

```bash
cep_codegen https://example.com
```

Or equivalently:

```bash
npx playwright codegen https://example.com
```

Two windows appear on your desktop:

1. **The browser** — navigate and interact with the target site as a
   normal user would.
2. **The Playwright Inspector** — shows the generated code as you click,
   type, and navigate.  Use the toolbar to:
   - **Record** — start/stop recording interactions
   - **Pick locator** — hover over elements to see Playwright's
     suggested selector
   - **Assert visibility / text / value** — add assertions without
     writing code

When you're done, copy the generated code from the Inspector into your
`*.test.ts` file.  The output is standard Playwright — wrap it in a
`test()` block, adjust selectors if needed, and you have a working test.

**Tip**: Codegen is especially useful for navigating complex forms,
cookie consent dialogs, and multi-step wizards where figuring out the
right selectors by hand would be tedious.  Record the flow first, then
refine the selectors and add assertions.

### Chrome Flags Are Handled Automatically

The container wraps the Chromium binary to inject GPU-disable flags
(software rendering) and Wayland display forwarding.  This means:

- **You don't need GPU flags in `playwright.config.ts`** — the container
  forces `--disable-gpu --use-gl=swiftshader` and related flags at the
  binary level, before Playwright even launches.
- **Wayland/X11 just works** — the wrapper detects `WAYLAND_DISPLAY`
  and injects `--ozone-platform=wayland` automatically.
- **Every Playwright command benefits** — `test`, `test --headed`,
  `codegen`, and manual Node.js scripts all go through the same wrapper.

A minimal `playwright.config.ts` is sufficient:

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 30000,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
```

No `launchOptions.args` needed — the container handles it.

### Viewport Size for Headed Mode

When running tests in headed mode (visible browser on your desktop),
consider enlarging the viewport beyond the default 1280x720.  A larger
viewport (e.g. 1920x1080) ensures that interactive elements are not
clipped or pushed off-screen, which can cause image matching and click
actions to miss their targets.

Set the viewport in the test file using `test.use()`, not in
`playwright.config.ts`, so the config stays reusable:

```typescript
const VIEWPORT = { width: 1920, height: 1080 };
test.use({ viewport: VIEWPORT });
```

This is especially important for forms and multi-step wizards where
buttons like "Weiter" or "Senden" may sit below the fold at smaller
viewports.

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
| `CEP_VNC` | (unset) | VNC fallback — required on Wayland when running vision tests (see below) |

Example — faster pace:

```bash
CEP_SPECTATE=1 CEP_SLOW_MO=150 CEP_VISION_HIGHLIGHT_MS=800 \
  pytest tests/integration/test_modes.py -k "vision_example and local" -v
```

#### Spectate Mode on Wayland with Vision Tests (`CEP_VNC=1`)

**Problem**: On a Wayland desktop, `CEP_SPECTATE=1` forwards the Wayland compositor
socket into the container. Chromium then uses its `--ozone-platform=wayland`
compositing pipeline, which produces slightly different pixel values in CDP
screenshots (`page.screenshot()`) compared to headless mode. Vision tests use
reference images captured headlessly, so the pixel difference causes failures even
though the test logic is correct.

**Solution**: Add `CEP_VNC=1`. This injects `--vnc`, which makes the container start
an internal Xtigervnc server instead of forwarding the Wayland socket. Chromium
connects to the Xtigervnc X11 display and uses the X11 rendering path, whose CDP
screenshot pixel values match the headless baseline. The test passes, and the
browser is visible via a VNC viewer.

```bash
# Wayland + vision tests: use CEP_VNC=1
CEP_SPECTATE=1 CEP_VNC=1 pytest tests/integration/test_modes.py -k "vision_example and local" -v
```

When `CEP_VNC=1` is active, `check_cep` prints the connect command to stderr:

```
VNC: connect with:  vncviewer SecurityTypes=None 127.0.0.1::5900
```

Open a second terminal and run that command before the container's Xtigervnc server
starts accepting connections (~4 seconds after the container starts). The VNC viewer
may prompt to reconnect once.

**When is `CEP_VNC=1` needed?**

| Desktop | Has vision tests | Use |
|---------|-----------------|-----|
| Wayland (Fedora, Ubuntu 22.04+, KDE 6) | Yes | `CEP_SPECTATE=1 CEP_VNC=1` |
| Wayland | No | `CEP_SPECTATE=1` |
| X11 | Yes or No | `CEP_SPECTATE=1` |

If you are not sure which display server you are running: `echo $WAYLAND_DISPLAY`
returns a non-empty value (e.g. `wayland-0`) on Wayland.

**Host requirement**: `vncviewer` must be installed on the host machine.
On Fedora: `dnf install tigervnc`. On Debian/Ubuntu: `apt install tigervnc-viewer`.

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

## Lightpanda Browser (Experimental)

> **Work in progress — no guarantees.**  Lightpanda is an alternative
> headless browser engine that promises 9x less memory and 11x faster
> execution than Chromium for DOM-only workloads.  CDP compatibility is
> still incomplete, so it only works for really simple web pages today.
> If it doesn't work for your test, use Chromium (the default).

### What Works

Single navigation + read-only DOM queries:

```typescript
test('simple page check', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(page.locator('h1')).toContainText('Example Domain');
  await expect(page.locator('p').first()).toContainText('documentation examples');
});
```

### What Does NOT Work

- `page.goto()` a second time (crashes the CDP server)
- `page.locator(sel).fill(text)` (crashes)
- `page.locator(sel).click()` when it triggers navigation (crashes)
- Complex or JS-heavy sites (segfault during load)
- Vision matching (no rendering engine)
- Headed mode (headless only)

### Running with Lightpanda

```bash
python3 src/check_cep ... --browser lightpanda
```

No changes to your test files are needed — a monkey-patch redirects
Playwright's `chromium.launch()` to Lightpanda's CDP endpoint
transparently.

### Why This Matters

Should Lightpanda's CDP support mature, it could dramatically reduce
the resource footprint of check_cep monitoring.  A Chromium container
needs ~500 MB RAM; Lightpanda targets ~50 MB for the same DOM workload.
For monitoring setups running dozens of browser checks, this would be
a significant improvement.

For technical details, see
[docs/lessons-learned/005-lightpanda-browser.md](docs/lessons-learned/005-lightpanda-browser.md).

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
