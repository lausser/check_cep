# VERIFICATION — MovingElement

## Verified

- The badge is clicked wherever the seeded sequence places it, via an image-template match.
- The status flips to 'Caught the badge!'.

## Assumed

- The template `assets/badge.png` matches the badge regardless of its (moving) position.

## Cannot / must NOT verify

- Absolute coordinates or a CSS path — the target moves every visit, so those are invalid by design.

## How to run offline

```bash
NM="$PWD/../../../../src/container/node_modules"
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```
