# tc_marketplace_preview_tile

Marketplace-style fixture inspired by visually noisy shopping homepages: dense banners,
mixed categories, many colorful pseudo-photo tiles, and repeated secondary labels.

## What it proves

- The page can be intentionally chaotic and still deterministic.
- The intended product is found by matching a small screenshot of its preview tile,
  not by text selectors or the CTA button.
- Two beauty items deliberately use very similar preview art, so the small image crop
  is ambiguous globally and only becomes safe when scoped to the target tile region.
- Only the matched article opens, even though the page is full of distractors from
  clothes, electronics, tools, accessories, and beauty/health.

## Fixture strategy

- Each product card has a vivid `photo-frame` built from deterministic inline SVG art.
- The committed template is a crop of the target product's preview image area.
- A neighboring distractor tile uses near-identical dryer imagery to make the match harder.
- The test uses `clickByImage()` with a click offset so the preview match opens the tile.

## Re-capturing templates

```bash
podman run --rm \
  --volume ./tests/fixtures/tc_marketplace_preview_tile:/home/pwuser/tests:rw,z \
  check_cep:test \
  node /home/pwuser/tests/capture-templates.mjs
```
