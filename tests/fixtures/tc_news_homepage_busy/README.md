# tc_news_homepage_busy

Deterministic news-homepage fixture with a sticky masthead, dense article cards,
repeated `Read story` CTAs, and a cookie banner that genuinely blocks the intended
 lower-page action until it is dismissed.

## What it proves

- A broad CTA search is unsafe on a clutter-heavy homepage because many identical buttons are visible.
- Cookie dismissal is a real prerequisite for the target action.
- A guided region strategy opens only the intended story after the banner is gone.

## Hard-but-fair design

- The page uses repeated CTA buttons, duplicated topic labels, and colorful promo blocks
  to mimic a busy media homepage.
- The target story is fully solvable after banner dismissal because the content is local,
  stable, and still fully visible.
- The fixture does not rely on random ads, live content, or unstable personalization.

## Files

- `pages/news.html` - self-contained homepage fixture
- `functions/index.ts` - asset paths and target story region
- `capture-templates.mjs` - regenerates `assets/story-btn.png` and `assets/accept-btn.png`

## Re-capturing templates

```bash
podman run --rm \
  --volume ./tests/fixtures/tc_news_homepage_busy:/home/pwuser/tests:rw,z \
  check_cep:test \
  node /home/pwuser/tests/capture-templates.mjs
```
