# Lessons Learned: Image-Based Element Matching in Playwright (Spec 002)

**Branch**: `002-test-env-setup` | **Date**: 2026-03-08

---

## Context

During spec 002 (test environment setup), an `imageMatching.ts` helper library
was added alongside the DOM-based Playwright tests. The goal was to provide a
secondary approach for locating UI elements — using reference screenshots and
OpenCV template matching instead of CSS/ARIA selectors.

This mirrors the dual-locator strategy from Sakuli (SikuliX image recognition +
Sahi DOM selectors) that check_cep aims to modernize.

## Approach

**Library**: `imageMatching.ts` (243 LOC), bundled alongside test fixtures.

**Dependencies added to the container**:
- `opencv-wasm` 4.3.0-10 — WebAssembly build of OpenCV for template matching
- `pngjs` 7.0.0 — PNG decode/encode for screenshot processing

**How it worked**:
1. Capture a full-page or region screenshot via `page.screenshot()`
2. Decode both screenshot and reference PNG to raw pixel buffers
3. Convert RGBA to grayscale, apply 3x3 Gaussian blur (reduce anti-aliasing noise)
4. Run `cv.matchTemplate()` with `TM_CCOEFF_NORMED` correlation
5. Compare `maxVal` against a confidence threshold (default 0.86)
6. Poll with configurable timeout (default 5s) and interval (default 200ms)

**API surface**:
- `findImageOnScreen(page, templatePath, options)` — core polling matcher
- `waitForImage()` — throws on timeout
- `clickByImage()` — match + click at center coordinates
- `typeByImage()` — match + click + keyboard type
- `clickImageOrLocator()` — hybrid: try DOM locator first, fall back to image

## Why It Failed

### 1. Anti-aliasing and subpixel rendering destroy score stability

The same "Logout" button rendered at different times produced wildly different
pixel patterns due to:
- **Subpixel font rendering**: Chromium's text rasterizer produces slightly
  different glyph bitmaps depending on element position, viewport size, and
  GPU state.
- **Anti-aliasing**: Edge pixels around buttons and text vary between renders.
- **ClearType / font hinting**: The headless Chromium in the container uses
  different hinting than the environment where reference images were captured.

Even with Gaussian blur pre-processing (3x3 kernel), match scores for the
same visual element fluctuated between 0.3 and 0.7 across runs — well below
the 0.86 default threshold.

### 2. Confidence threshold is a lose-lose tradeoff

- **High confidence (>0.8)**: Consistent false negatives. The element is
  visually present but pixel differences from rendering variance cause misses.
- **Low confidence (<0.5)**: False positives. Unrelated regions of the page
  score above threshold. The test used 0.4 for the logout button and still
  failed intermittently.
- There is no stable middle ground because the score distribution for
  "present" and "absent" overlaps significantly.

### 3. Resolution and viewport sensitivity

The reference image must match the exact viewport dimensions and device pixel
ratio. The container's headless Chromium defaults (1280x720, DPR 1) differ
from most development environments. A reference image captured at DPR 2
simply cannot match at DPR 1 — the template is physically larger than the
rendered element.

### 4. Operational fragility in CI/container environments

- Reference images must be regenerated whenever the target site changes its
  CSS, even for cosmetic tweaks (color, padding, border-radius).
- Different Playwright/Chromium versions produce different rendering output,
  requiring reference image updates on every version bump.
- Headless vs. headed mode renders text differently (no GPU compositing in
  headless), so references from one mode don't work in the other.

### 5. Performance overhead

Each poll iteration takes a full-page screenshot (~50-100ms), decodes PNG,
runs OpenCV template matching (~20-50ms). With 200ms polling interval and
5s timeout, a failing match burns 3-5 seconds per element. Multiply by
several image-matched elements and test runtime balloons.

## What Was Removed

- `tests/fixtures/tc_register_pass/imageMatching.ts` — the helper library
- `tests/fixtures/tc_register_pass/images/logout.png` — reference screenshot
- `opencv-wasm` and `pngjs` from `src/container/package.json`
- The `clickByImage()` call in `tc_register_pass.test.ts` (replaced with
  `page.locator('a[href="/logout"]').click()`)

## Key Takeaways

1. **OpenCV template matching is not suited for DOM-rendered UI testing.**
   It works for bitmap-stable targets (desktop apps, game UIs, terminal
   screenshots) but web content has too much rendering variance.

2. **Playwright's built-in locators are the right default.** CSS selectors,
   ARIA roles, `getByText()`, and `getByRole()` are immune to rendering
   variance and orders of magnitude faster.

3. **Image-based matching may still have a role** for:
   - Canvas/WebGL content where no DOM exists
   - PDF viewers or embedded images
   - Visual regression testing (comparing full pages, not locating elements)
   - Desktop UI elements via Playwright's `electron` or external tools

4. **If revisiting image matching**, consider:
   - Playwright's built-in `toHaveScreenshot()` for visual regression (uses
     pixelmatch with configurable threshold, handles anti-aliasing properly)
   - Perceptual hashing (pHash/dHash) instead of template matching — more
     tolerant of rendering variance
   - SSIM (structural similarity) which is designed for comparing rendered
     content
   - Codex agent's ongoing experiments with alternative approaches

## Related

- Codex agent is separately experimenting with image locator approaches —
  that work may feed into a future spec
- Sakuli's SikuliX used Java-based OpenCV with more sophisticated matching
  (multi-scale, edge detection) but still suffered from similar fragility
  in web contexts
