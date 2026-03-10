# tc_vision_example_form

Multi-field contact form fixture demonstrating three selector strategies
side by side: **vision-only**, **DOM-only**, and **hybrid** (vision-first
with DOM fallback).

## Fixture structure

```
tc_vision_example_form/
  assets/                  # Persistent template PNGs (committed)
  functions/index.ts       # Shared helpers: asset(), assertFormFilled(), constants
  variables/index.ts       # Test data: FORM_DATA
  pages/form.html          # Self-contained form page (inline CSS, Arial only)
  playwright.config.ts     # Render baseline (1280x720, deviceScaleFactor: 1)
  tc_vision_example_form.test.ts
  capture-templates.mjs    # Standalone script to regenerate assets/
```

## Template strategy

Template images in `assets/` capture the full **field row** (label + input)
rather than just the bare input element.  Including the label text ensures
each template is visually unique — without it, all three empty text inputs
would be indistinguishable to the vision matcher.

## Click offsets

Because the row center falls on the label, a `clickOffset` shifts the click
into the input area.  The offset values are derived from the template
dimensions (424x42 px) and the known label width (~110 px).

## Region strategy

All vision calls use `region: 'main'` to constrain matching to the page
center, reducing the search area and avoiding false matches in the
gradient background.

## Re-capturing templates

If `pages/form.html` changes, re-run the capture script inside the
container:

```bash
podman run --rm \
  --volume ./tests/fixtures/tc_vision_example_form:/home/pwuser/tests:rw,z \
  check_cep:test \
  node /home/pwuser/tests/capture-templates.mjs
```

## What the three tests demonstrate

| Test | Approach | Use case |
|------|----------|----------|
| Vision-only | `typeByImage` / `clickByImage` | Pure visual — no DOM knowledge needed |
| DOM-only | `page.locator().fill()` / `.click()` | Standard Playwright — fast and precise |
| Hybrid | `typeByImageOr` / `clickByImageOr` | Production recommended — resilient fallback |
