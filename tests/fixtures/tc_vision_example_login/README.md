# tc_vision_example_login

Realistic login flow on a visually busy page demonstrating vision-based
form interaction with persistent templates.

## Fixture structure

```
tc_vision_example_login/
  assets/                  # Persistent template PNGs (committed)
  functions/index.ts       # Shared helpers: asset(), LOGIN_URL, LOGIN_CARD, assertLoginSubmitted()
  pages/login.html         # Self-contained login page (inline CSS, Arial only)
  playwright.config.ts     # Render baseline (1280x720, deviceScaleFactor: 1)
  tc_vision_example_login.test.ts
  capture-templates.mjs    # Standalone script to regenerate assets/
```

## Template choices

- **username-field.png** / **password-field.png**: Capture the full form
  group (label + input) rather than just the input.  The "Username" and
  "Password" labels disambiguate what would otherwise be two identical
  text inputs.

- **signin-cta.png**: The primary "Sign In" button is a solid blue,
  full-width CTA.  It is visually distinct from the social login buttons
  (outlined/dark background), so template matching correctly targets the
  CTA without ambiguity.

## Region strategy

All vision calls are scoped to the `LOGIN_CARD` region, which covers the
centered login form.  This excludes the navbar, hero banner, feature cards,
and footer from the search area, improving both accuracy and speed.

## Why no clickOffset is needed

The form-group templates are 300x61 px.  The label occupies the top ~20 px
and the input the lower ~41 px.  The center-click at y=30 lands inside the
input area, so no offset adjustment is required.

## What the two tests demonstrate

| Test | Approach | Use case |
|------|----------|----------|
| Vision-only | `typeByImage` / `clickByImage` | Pure visual — no DOM knowledge needed |
| Hybrid | `typeByImageOr` / `clickByImageOr` | Production recommended — resilient fallback |

The vision-only test includes `debugDir` / `debugLabel` on the username
field as an example of generating diagnostic artifacts.

## Re-capturing templates

If `pages/login.html` changes, re-run the capture script inside the
container:

```bash
podman run --rm \
  --volume ./tests/fixtures/tc_vision_example_login:/home/pwuser/tests:rw,z \
  check_cep:test \
  node /home/pwuser/tests/capture-templates.mjs
```
