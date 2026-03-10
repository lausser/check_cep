# tc_vision_example_console

Dense admin dashboard fixture demonstrating **ambiguity rejection** and
**region-guided resolution** with `check-cep-vision`.

## Fixture structure

```
tc_vision_example_console/
  assets/                  # Persistent template PNGs (committed)
  functions/index.ts       # Shared helpers: asset(), CONSOLE_URL
  pages/console.html       # Self-contained dashboard (inline CSS, Arial only)
  playwright.config.ts     # Render baseline (1280x720, deviceScaleFactor: 1)
  tc_vision_example_console.test.ts
  capture-templates.mjs    # Standalone script to regenerate assets/
```

## Why the broad search fails

The dashboard has six identically-styled "Delete job" buttons across two
panels.  A region-free `locateByImage` finds multiple matches with nearly
identical confidence scores.  The vision matcher rejects this as ambiguous
(score gap below `DEFAULT_AMBIGUITY_GAP`) — this is correct, safe behaviour.

## How regions resolve it

By passing a `RectRegion` that covers only the first row of the right panel,
the search area is restricted to a single button.  Even scoping to the whole
panel would still be ambiguous (3 identical buttons), so we narrow further to
the specific row.  The region coordinates come from the row's bounding box at
the 1280x720 render baseline.

## Debug artifacts

The region-scoped test uses `debugDir` and `debugLabel` to write diagnostic
artifacts (region crop, annotated screenshot, match metadata) to the results
directory.  These are invaluable for post-mortem inspection when a match
fails or scores lower than expected.

## Re-capturing templates

If `pages/console.html` changes, re-run the capture script inside the
container:

```bash
podman run --rm \
  --volume ./tests/fixtures/tc_vision_example_console:/home/pwuser/tests:rw,z \
  check_cep:test \
  node /home/pwuser/tests/capture-templates.mjs
```

## Choosing regions for your own pages

1. Open the page at the render baseline (1280x720, deviceScaleFactor: 1).
2. Use browser DevTools or a Playwright script to get the bounding box of
   the container element you want to isolate.
3. Add a small margin (5-10 px) to account for minor rendering differences.
4. Pass the region as `{ x, y, width, height }` to the vision call.
