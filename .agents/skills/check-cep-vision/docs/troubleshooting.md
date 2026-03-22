# Troubleshooting Vision Test Failures

Diagnostic guide for common check-cep-vision failure modes. Use this when a vision test fails and you need to determine why and how to fix it.

## Step 1: Read the Error Message

Vision failures include structured information. The error message format:

```
Image match failed: reason=<reason> confidence=0.9000 best=0.8742 color=0.8523 gray=0.9010
```

- `reason`: What went wrong (see failure modes below)
- `confidence`: The threshold that was required
- `best`: The best candidate's combined score
- `color`: Color verification score
- `gray`: Grayscale match score

## Step 2: Check Debug Artifacts

If `debugDir` was set, examine three files:

| File | What It Shows |
|------|--------------|
| `{label}-region.png` | The raw screenshot of the searched region |
| `{label}-annotated.png` | Same screenshot with red rectangle around best match |
| `{label}-meta.json` | Structured metadata: scores, positions, region info |

### Reading meta.json

```json
{
  "reason": "ambiguous",
  "confidence": 0.9,
  "ambiguityGap": 0.03,
  "bestCandidate": {
    "x": 792, "y": 245,
    "combinedScore": 0.9512,
    "colorScore": 0.9434,
    "score": 0.9607
  },
  "secondCandidate": {
    "x": 792, "y": 310,
    "combinedScore": 0.9489,
    "colorScore": 0.9401,
    "score": 0.9596
  }
}
```

Key fields:
- `reason`: The failure type
- `bestCandidate.combinedScore`: How well the best match scored
- `secondCandidate.combinedScore`: How well the runner-up scored
- Gap = best - second: If < 0.03, it's ambiguous

## Failure Mode: `not-found`

**Meaning**: No candidate scored above the confidence threshold (default 0.9).

### Diagnosis Flow

1. **Check the annotated PNG**: Is the target element visible on the page?
   - Not visible → the page state is wrong (wrong URL, content not loaded, modal covering it)
   - Visible but no rectangle → the template doesn't match the current rendering

2. **Check render baseline match**:
   - Template captured at different viewport? (e.g., 1920x1080 vs 1280x720)
   - Template captured at different DPR? (e.g., DPR 2 on macOS vs DPR 1 in container)
   - Template captured outside the container? (different font rendering)
   - Solution: Re-capture template inside the container at 1280x720, DPR 1

3. **Check template quality**:
   - Is the template too generic? (bare input field with no label)
   - Does the template include dynamic content? (timestamps, counters)
   - Solution: Crop tighter, include labels, avoid dynamic elements

4. **Check if the element has changed**:
   - CSS redesign? Different colors, padding, font size?
   - Solution: Re-capture the template

5. **Check the region**: Is the target actually within the specified region?
   - Look at `effectiveRegion` in meta.json
   - The target may be outside the region bounds
   - Solution: Adjust region or use a different preset

### Fixes (in order of preference)

1. Re-capture the template under the correct baseline
2. Adjust the search region to include the target
3. Increase `timeoutMs` if the element appears asynchronously
4. **Last resort**: Lower `confidence` slightly (e.g., 0.85) — but this usually masks the real problem

## Failure Mode: `ambiguous`

**Meaning**: The best candidate scored above threshold, but the second-best scored too close (gap < 0.03).

### Diagnosis Flow

1. **Check the annotated PNG**: Are there multiple similar elements visible?
   - Multiple identical buttons in a table → classic ambiguity
   - Same element appearing in different locations → layout issue

2. **Check meta.json**: Compare bestCandidate and secondCandidate positions
   - Same row, different columns → horizontal duplicates
   - Same column, different rows → vertical duplicates (e.g., table rows)

### Fixes (in order of preference)

1. **Narrow the region** to include only one instance of the target
   ```typescript
   const FIRST_ROW = { x: 100, y: 230, width: 500, height: 65 };
   await vision.clickByImage(page, template, { region: FIRST_ROW });
   ```

2. **Improve the template crop** — include more surrounding context that differs between instances

3. **Use the staged anchor pattern** — find a unique nearby element first, then derive a region

4. **DO NOT lower `ambiguityGap`** — this masks real ambiguity and leads to wrong clicks

## Failure Mode: `invalid-template`

**Meaning**: The template PNG has no opaque pixels (fully transparent image).

### Fix
- The template file is corrupted or was saved incorrectly
- Re-capture the template
- Verify the PNG has visible content (not all-transparent)

## Failure Mode: `unreadable-template`

**Meaning**: The template file could not be read (missing file, wrong path, corrupted PNG).

### Fix
- Check the file path — is it relative to the test's working directory?
- Inside the container, templates are at `/home/pwuser/tests/<test-name>/assets/`
- Verify the file exists and is a valid PNG

## Failure Mode: `invalid-region`

**Meaning**: The specified region is outside the viewport or has zero dimensions.

### Fix
- Check region coordinates against the viewport (1280x720)
- Named presets are always valid — this only happens with custom rectangles
- Ensure x + width <= 1280 and y + height <= 720

## Failure Mode: `invalid-options`

**Meaning**: `region` and `fullPage` were both specified. These are mutually exclusive.

### Fix
- Use either `region: 'main'` OR `fullPage: true`, never both
- Remove one of the conflicting options

## Failure Mode: `invalid-size`

**Meaning**: The template is larger than the search region.

### Fix
- The template is too big for the specified region
- Use a larger region or re-capture a smaller template crop
- Check if the region is being clipped to a very small area

## Failure Mode: `scoring-failed`

**Meaning**: Grayscale candidates were found but color verification produced no valid scores.

### Fix
- This is rare — usually indicates a corrupted template or unusual color space issue
- Re-capture the template
- Check if the template has unusual alpha channel values

## Quick Reference: Score Interpretation

| Combined Score | Meaning |
|---------------|---------|
| 0.95 – 1.00 | Excellent match — pixel-perfect or near-perfect |
| 0.90 – 0.95 | Good match — minor rendering differences |
| 0.85 – 0.90 | Borderline — likely a different render or slightly wrong template |
| Below 0.85 | Poor match — wrong template, wrong baseline, or wrong element |

## Quick Reference: Common Fixes

| Symptom | Most Likely Fix |
|---------|----------------|
| `not-found`, score 0.85-0.89 | Re-capture template or adjust region |
| `not-found`, no candidates | Template captured at wrong baseline |
| `ambiguous`, table of buttons | Narrow region to specific row |
| `ambiguous`, same element twice | Layout has hidden duplicates — check DOM |
| `invalid-template` | Re-capture, check PNG is not transparent |
| Works locally, fails in container | Template captured outside container (font difference) |
