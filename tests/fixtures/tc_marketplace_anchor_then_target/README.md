# tc_marketplace_anchor_then_target

Marketplace-style fixture that demonstrates staged recovery: a small preview crop is ambiguous globally, so the test first matches a unique anchor badge and then uses that region to click the intended preview.

## What it proves

- The page stays noisy and repetitive while remaining deterministic.
- The target preview image is not unique enough to use globally.
- A first match can recover a safe region for a second match without DOM geometry.
- Only the intended dryer tile opens; the similar neighboring dryer stays untouched.

## Fixture strategy

- Two dryer tiles use nearly identical preview art to force global ambiguity.
- The target tile adds a unique `Night Sale` anchor badge captured as its own template.
- The test uses `locateByImage()` on the badge, derives a staged region from `bestCandidate`, then uses `clickByImage()` on the preview template inside that recovered region.
- The final assertion verifies state change on the target tile only.

## Re-capturing templates

```bash
podman run --rm \
  --volume ./tests/fixtures/tc_marketplace_anchor_then_target:/home/pwuser/tests:rw,z \
  check_cep:test \
  node /home/pwuser/tests/capture-templates.mjs
```
