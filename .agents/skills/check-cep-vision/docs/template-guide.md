# Template Creation Guide

Templates are the visual selectors that drive check-cep-vision. A template is a
tightly cropped PNG screenshot of the UI element you want to locate, click, or
type into. Because matching is pixel-level, capture conditions must exactly
reproduce the test runtime. This guide covers capture, cropping, naming, and
maintenance.

---

## The Render Baseline

Templates MUST be captured under identical conditions to the test runtime:

| Parameter            | Required Value                         |
|----------------------|----------------------------------------|
| Viewport             | 1280 x 720                             |
| Device scale factor  | 1 (no HiDPI / Retina)                  |
| Browser              | Playwright-bundled Chromium             |
| Animations           | disabled                               |
| Caret                | hidden (`caret: 'hide'`)               |
| Fonts                | Container defaults (Arial, sans-serif) |

If template and runtime differ on ANY of these, the match will fail. This is
intentional -- determinism is the foundation of reliable image matching. A
template captured in your local Chrome on macOS with Retina scaling will not
match the same element rendered inside the container at DPR 1.

See [examples/playwright.config.ts](../examples/playwright.config.ts) for the
standard configuration that enforces this baseline.

---

## Capture Workflow

1. **Write a standalone capture script** (see `examples/capture-templates.mjs`).
2. **Run it INSIDE the check_cep container** for consistent rendering. Never
   capture from a browser running on the host.
3. **Use element-level screenshots**, not full-page crops:
   ```javascript
   const row = page.locator('.form-group:has-text("Username")');
   await row.screenshot({ path: 'assets/username-row.png' });
   ```
4. **Save PNGs to the test's `assets/` directory:**
   ```
   my-test/
     my-test.spec.ts
     assets/
       username-row.png
       password-row.png
       submit-btn.png
   ```
5. **Commit templates to version control** alongside the test. Templates are
   source artifacts, not build output.

### Capture script skeleton

```javascript
// capture-templates.mjs -- run inside the container
import { chromium } from 'playwright';

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();
await page.addStyleTag({ content: '* { caret-color: transparent !important; }' });
await page.goto('https://target-app.example.com/login');
await page.waitForLoadState('networkidle');

await page.locator('label:has-text("Username") + input').screenshot({
  path: 'assets/username-row.png',
});
await page.locator('button:has-text("Log in")').screenshot({
  path: 'assets/login-btn.png',
});
await browser.close();
```

---

## Crop Rules

### Include labels with inputs

Bare input fields all look identical. The label text makes each field unique.

```
Good (label + input):              Bad (bare input):
+---------------------------------+    +----------------------+
|  Name    [________________]     |    | [________________]   |
+---------------------------------+    +----------------------+
Unique -- label text differs            Generic -- matches any input
```

Always capture the label and the control together.

### Tight crops

- Include enough visual context to be unique, but not so much that surrounding
  noise changes between runs.
- For **buttons**: crop tightly around the button including its text label.
- For **icons**: include enough surrounding context to disambiguate.
- For **table cells**: include the column header or row label if the cell value
  alone is not unique.

### Avoid dynamic content

- NO timestamps, counters, or animated elements in templates
- NO cursor/caret in templates (use `caret: 'hide'` when capturing)
- NO hover effects (capture in default state)
- NO user-specific content (avatars, usernames) unless testing that element

---

## Click Offsets

When a template includes label + input, the match center falls on the label.
Use `clickOffset` to shift the click into the input:

```typescript
await vision.typeByImage(page, 'assets/name-row.png', 'Alice', {
  clickOffset: { x: 300, y: 21 },  // Shift right into the input
});
```

### How to determine offset values

1. Open the template image in an image editor.
2. Note total dimensions (e.g., 500 x 42 pixels). The default click point is
   the center: (250, 21).
3. Find the pixel coordinates of the desired click target (e.g., middle of the
   input field at (450, 21)).
4. Compute offset from center: `clickOffset.x = 450 - 250 = 200`,
   `clickOffset.y = 21 - 21 = 0`.

---

## Template Naming Conventions

Use descriptive, lowercase, hyphenated names:

| Pattern | Example |
|---------|---------|
| `<element>-<type>.png` | `submit-btn.png`, `search-icon.png` |
| `<section>-<field>-row.png` | `login-username-row.png`, `login-password-row.png` |
| `<page>-<element>.png` | `dashboard-sidebar-toggle.png` |

When multiple templates exist for the same element in different states, add a
state suffix: `submit-btn-disabled.png`.

---

## When Templates Stop Working

Templates break when the rendered pixels change:

| Cause | Symptom | Fix |
|-------|---------|-----|
| CSS / design update | `not-found` | Re-capture inside the container |
| Font rendering change (container update) | `not-found` | Re-capture inside the container |
| Viewport or DPR mismatch | `not-found` | Verify Playwright config matches baseline |
| Template captured outside container | `not-found` | Re-capture inside the container |
| Dynamic content in template | Intermittent `not-found` | Crop out the dynamic portion |
| Too-generic crop | `ambiguous` | Include more context (labels, headers) |

The fix is almost always: **re-capture templates inside the container under the
standard baseline.**

---

## Template Quality Checklist

- [ ] Captured inside the check_cep container (not from local browser)
- [ ] Viewport 1280x720, DPR 1
- [ ] Animations disabled
- [ ] Caret hidden
- [ ] Tight crop with labels included
- [ ] No dynamic content (timestamps, cursors, hover effects)
- [ ] Descriptive filename
- [ ] Saved in the test's `assets/` directory
- [ ] Committed to version control
