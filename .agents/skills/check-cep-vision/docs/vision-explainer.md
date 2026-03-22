# How check-cep-vision Finds UI Elements

## Overview

check-cep-vision uses OpenCV template matching to locate UI elements by their
visual appearance rather than DOM structure. It is a Playwright add-on running
inside the check_cep container. The library takes a small PNG screenshot of a
target element (the "template") and searches for it within a screenshot of the
current page (the "source").

No native binaries, no ML models, no OCR. The system is deterministic and
explainable: every match decision can be traced back to pixel-level arithmetic.

## Technology Stack

| Package | Role | Size |
|---------|------|------|
| `opencv-wasm` | WebAssembly build of OpenCV -- provides `cv.matchTemplate()` | ~4 MB WASM binary, no native deps |
| `pngjs` | Pure-JavaScript PNG encoder/decoder | ~50 KB |

Both run inside Node.js. The WASM binary is platform-independent: same binary
on any OS and architecture. The trade-off vs native OpenCV is speed, but for
matching a small template against a single screenshot it is more than fast
enough (typically 50-150 ms per match attempt).

There is no neural network, no ML model, no OCR engine. Template matching is
classical computer vision: a sliding window of normalized cross-correlation
over pixel grids.

## The Two-Stage Matching Pipeline

A naive implementation would run full-color template matching across the entire
screenshot at a single scale. check-cep-vision uses a two-stage pipeline that
is both faster and more accurate:

```
  Stage 1                          Stage 2
  -------                          -------
  Grayscale candidate              Color verification
  generation                       of top candidates
      |                                |
      |  +---------------------+       |  +---------------------+
      +--| Convert to grayscale|       +--| Per-pixel RGBA      |
      |  | (discard color)     |       |  | comparison           |
      |  +---------------------+       |  +---------------------+
      |  +---------------------+       |  +---------------------+
      +--| Run matchTemplate() |       +--| Alpha-aware          |
      |  | at 3 scales         |       |  | (skip transparent px)|
      |  +---------------------+       |  +---------------------+
      |  +---------------------+       |  +---------------------+
      +--| Collect top ~4      |       +--| Weighted combine:    |
         | candidate positions |          | 0.45*gray + 0.55*clr|
         +---------------------+          +---------------------+
```

### Stage 1: Fast Grayscale Candidate Generation

Both the source screenshot and the template are converted from RGBA to
single-channel grayscale (luminance). This collapses all color information into
a single brightness value per pixel.

OpenCV's `cv.matchTemplate()` with `TM_CCOEFF_NORMED` slides the template
across every position in the source and computes a normalized cross-correlation
score at each one:

- **1.0** = perfect pixel-pattern match
- **0.0** = no correlation
- **-1.0** = inverse correlation

The result is a matrix of dimensions `(W - w + 1) x (H - h + 1)`, where
`W x H` is the source size and `w x h` is the template size. For a 1280x720
source and 100x40 template, that is 1181 x 681 = 804,261 scores.

Rather than sorting this entire matrix, the implementation maintains a small
**bounded buffer** during a single scan pass. The buffer holds the top entries
(sized at `limit * 12`, where limit is typically 4), inserting by score and
trimming overflow. After scanning, overlapping candidates (overlap ratio > 0.5)
are deduplicated, keeping only the strongest non-overlapping positions.

This runs at three scales (see below), and candidates from all scales compete
in the same pool. After cross-scale collection, a second deduplication pass
(overlap threshold 0.45) produces the final candidate set.

**Why grayscale first:**
- Fast -- single channel means 1/4 the data vs RGBA
- Excellent at finding structural/shape matches (text glyphs, borders, icons)
- Cannot distinguish elements that share shape but differ in color (a red button
  vs a blue button of identical dimensions look the same in grayscale)

That limitation is exactly what Stage 2 addresses.

### Stage 2: Color-Aware Verification

For each grayscale candidate, the library compares per-pixel RGBA values between
the original full-color template and the corresponding patch in the source:

```
For each candidate position (x, y):
  For each pixel in the template:
    if template pixel alpha == 0: skip (transparent)
    alpha_weight = template_alpha / 255
    diff += |template.R - source.R| * alpha_weight
    diff += |template.G - source.G| * alpha_weight
    diff += |template.B - source.B| * alpha_weight
    total_weight += 3 * alpha_weight

  color_score = max(0, 1 - (diff / total_weight) / 255)
```

The alpha channel is respected throughout: transparent template pixels are
skipped entirely, and semi-transparent pixels contribute proportionally.
Templates with irregular shapes or rounded corners work correctly because the
transparent border pixels do not pollute the score.

Out-of-bounds reads return `null` immediately, so a candidate that extends
past the source edge is discarded rather than producing corrupt scores.

**Why this stage is needed:**
A green "Approve" and red "Reject" button with identical dimensions and font
look the same in grayscale. Color verification distinguishes them. Without it,
the system would click the wrong button whenever two same-shaped elements
differ only by color.

### Score Combination

The two scores are combined with fixed weights:

```
final_score = 0.45 * grayscale_score + 0.55 * color_score
```

Color is weighted higher because it is the discriminating stage for visually
similar elements. The grayscale score still contributes because it captures
structural alignment that color alone might miss (thin borders, text glyph
shapes, sub-pixel edge patterns).

These weights are defined as `DEFAULT_SCORE_WEIGHTS = { gray: 0.45, color: 0.55 }`
in the source and are not currently configurable per-call.

### Decision Logic

After combining scores, the candidates are sorted by `combinedScore` descending.
Three outcomes are possible:

| Condition | Result | Meaning |
|-----------|--------|---------|
| `best_score >= 0.9` | **found** | Match accepted |
| `best_score >= 0.9` AND `best - second < 0.03` | **ambiguous** | Rejected even though score is high |
| `best_score < 0.9` | **not-found** | No match meets the threshold |

The confidence threshold (0.9) and ambiguity gap (0.03) are configurable via
`VisionOptions.confidence` and `VisionOptions.ambiguityGap`.

Ambiguity rejection is deliberate: in monitoring, a missed click fails loudly
and is easy to diagnose. A *wrong* click produces misleading results and
erodes trust. When ambiguity is detected, the solution is to narrow the search
area with regions (see below).

## Why Three Scales?

Web content can drift by a few percent between renders due to:
- Font hinting differences across Chromium versions
- Sub-pixel positioning and anti-aliasing
- Minor CSS rounding in percentage-based layouts

A template captured at exactly 100x40 pixels might appear on screen at 97x39
or 103x41. Single-scale matching would miss it.

check-cep-vision handles this with three scales:

| Scale | Effect |
|-------|--------|
| 0.97 | Template shrunk by 3% |
| 1.00 | Original size |
| 1.03 | Template enlarged by 3% |

Scaled templates are generated once per operation using nearest-neighbor
resampling (a simple pixel-copy loop, no interpolation library needed).
Candidates from all three scales compete in the same pool.

This band is deliberately minimal. A huge multi-scale pyramid would be
overkill in the controlled container environment where viewport and DPR
are fixed. The default scales are overridable via `VisionOptions.scales`.

## Regions: The #1 Reliability Lever

Region narrowing is the single most effective way to improve match quality.

**Without region:** The default is a center inset (~80% width, ~72% height),
NOT the full page. This is computed as:

```
x:      viewport.width  * 0.10   (128px on 1280-wide viewport)
y:      viewport.height * 0.14   (101px on 720-high viewport)
width:  viewport.width  * 0.80   (1024px)
height: viewport.height * 0.72   (518px)
```

Full-page search must be explicitly requested with `{ fullPage: true }`.

**Named presets** (all values for 1280x720 viewport):

| Preset | Pixel rect | Area (px) | Description |
|--------|-----------|-----------|-------------|
| `'header'` | `{0, 0, 1280, 130}` | 166,400 | Top 18% of viewport |
| `'main'` | `{128, 101, 1024, 518}` | 530,432 | Center inset (same as default) |
| `'footer'` | `{0, 576, 1280, 144}` | 184,320 | Bottom 20% of viewport |
| `'topLeft'` | `{0, 0, 640, 252}` | 161,280 | Left half, top 35% |
| `'topRight'` | `{640, 0, 640, 252}` | 161,280 | Right half, top 35% |
| `'left'` | `{0, 0, 640, 720}` | 460,800 | Left half, full height |
| `'right'` | `{640, 0, 640, 720}` | 460,800 | Right half, full height |

**Custom rectangles** give pixel-level control:

```typescript
const FIRST_ROW = { x: 740, y: 230, width: 530, height: 65 };
await vision.clickByImage(page, 'assets/delete-btn.png', { region: FIRST_ROW });
```

Custom regions are clipped to the viewport boundary -- if the rectangle extends
beyond the viewport edge, it is silently trimmed. A region that clips to zero
area is rejected as `invalid-region`.

**Why regions matter:**

1. **Eliminate ambiguity.** Six identical "Delete" buttons on a page produce
   ambiguous scores. Region-narrow to one row and only one button is in scope.
2. **Improve performance.** A 530x65 region is 96% smaller than the full
   viewport. Template matching is proportional to the search area.
3. **Document intent.** `region: 'header'` communicates where the target lives,
   making tests self-documenting.

**Constraint:** `region` and `fullPage` cannot be combined. The library rejects
this as `invalid-options`.

## What Works and What Doesn't

### Works well in the controlled container environment

The system thrives because the environment is tightly constrained:

- **Viewport** is fixed (1280x720)
- **Device pixel ratio** is fixed at 1
- **Fonts** are container-managed and deterministic
- **Browser** is a specific Playwright-bundled Chromium version
- **Animations** are disabled during capture

Under these conditions, the same page rendered twice produces near
pixel-identical output. Template matching has an extremely high
signal-to-noise ratio, which is why classical computer vision works and ML
is unnecessary.

### Does NOT work

- **Partially occluded elements.** If a modal covers half the button, the
  template will not match. The system correctly rejects this rather than
  guessing at a partial match.
- **Large CSS redesigns.** A redesign that changes button colors, padding,
  or font size invalidates templates. They must be re-captured.
- **DPR mismatches.** Templates captured at DPR 2 will not match at DPR 1.
  The pixel patterns are fundamentally different.
- **Dynamic content in templates.** If the template includes a timestamp or
  counter, it will differ on every page load. Templates should capture only
  stable visual elements.
- **Very small templates.** A template with too few opaque pixels has
  insufficient signal for reliable matching. The library validates that
  templates have opaque pixels and rejects fully transparent images.

## Debug Artifacts

When `debugDir` is set, the library writes three files per match attempt:

| File | Contents |
|------|----------|
| `{label}-region.png` | Raw screenshot of the searched region |
| `{label}-annotated.png` | Same screenshot with a red rectangle around the best match |
| `{label}-meta.json` | Structured metadata: scores, positions, region info, reason |

Example `meta.json` payload:

```json
{
  "reason": "found",
  "confidence": 0.9,
  "bestCandidate": {
    "x": 792, "y": 245,
    "width": 88, "height": 32,
    "score": 0.9812,
    "colorScore": 0.9734,
    "combinedScore": 0.9769
  },
  "secondCandidate": null
}
```

These artifacts are essential for troubleshooting failures without re-running
tests. The annotated screenshot shows exactly what the library saw and where
it thought the match was. The meta.json shows the numeric scores so you can
tell whether the failure was close (score 0.88 vs threshold 0.90) or
catastrophic (score 0.30).

Annotated images use `drawRect()` to paint a visible red rectangle directly
onto the screenshot pixel buffer before encoding to PNG.

## Performance Characteristics

- **Typical match time:** 50-150 ms per attempt (screenshot + decode + two-stage pipeline)
- **`waitForImage` polling:** Every 100 ms (`DEFAULT_POLL_MS`) up to 1200 ms timeout (`DEFAULT_TIMEOUT_MS`)
- **Region narrowing impact:** Dramatic. A 530x65 custom region vs full viewport reduces the result matrix from ~800K cells to ~30K cells -- roughly 25x fewer correlation computations.
- **Scale overhead:** 3x the matchTemplate calls vs single-scale, but each is fast. The scaled templates are cached once per operation via `buildScaledTemplateCache()`.
- **Template caching:** Scaled variants and opaque pixel counts are computed once and reused across polling iterations.

## Terminal vs Retriable Failures

The library distinguishes between failures that should be retried (the element
might appear on the next poll) and terminal failures that indicate a
configuration or template error:

**Terminal (never retried by `waitForImage`):**
- `invalid-size` -- template larger than search area
- `invalid-template` -- no opaque pixels
- `invalid-region` -- region clips to zero area
- `invalid-options` -- conflicting options (e.g., region + fullPage)
- `scoring-failed` -- OpenCV produced no finite scores
- `unreadable-template` -- PNG decode failed

**Retriable:**
- `not-found` -- no candidate met the confidence threshold (element may not have rendered yet)
- `ambiguous` -- multiple candidates too close in score (page may still be loading)

## Constants Reference

All defaults are defined at module scope and exposed via `vision.constants`:

```
DEFAULT_CONFIDENCE              = 0.9
DEFAULT_TIMEOUT_MS              = 1200
DEFAULT_POLL_MS                 = 100
DEFAULT_AMBIGUITY_GAP           = 0.03
DEFAULT_SCALES                  = [0.97, 1.0, 1.03]
DEFAULT_SCORE_WEIGHTS           = { gray: 0.45, color: 0.55 }
DEFAULT_CANDIDATE_BUFFER_MULTIPLIER = 12
```

The candidate buffer multiplier controls how many raw candidates are kept
during the result matrix scan before deduplication. With the default limit of
4 candidates and multiplier of 12, the buffer holds up to 48 entries during
scanning, then deduplication trims to the final 4.
