# tc_shop_catalog_grid

Deterministic shop-category fixture with a dense product grid, repeated `Add to cart`
buttons, colorful thumbnails, and a sticky filter bar.

## What it proves

- A broad button search is ambiguous on a busy catalog page.
- A card-scoped region isolates the intended product safely.
- Only the target card changes state after the guided click.

## Hard-but-fair design

- All twelve cards reuse the same CTA styling to create real ambiguity.
- The target card (`Nimbus Lamp`) has a distinctive badge and copy, but the green-path
  strategy is still region guidance rather than magical global matching.
- The page is visually cluttered, but fully deterministic: local HTML, fixed layout,
  no random ordering, no external images, and no animations.

## Files

- `pages/catalog.html` - self-contained catalog page
- `functions/index.ts` - asset paths and target card region
- `capture-templates.mjs` - regenerates `assets/add-btn.png`

## Re-capturing templates

```bash
podman run --rm \
  --volume ./tests/fixtures/tc_shop_catalog_grid:/home/pwuser/tests:rw,z \
  check_cep:test \
  node /home/pwuser/tests/capture-templates.mjs
```
