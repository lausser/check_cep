# VERIFICATION — NoStableLocator

## Verified

- The icon-only canvas control (no id/role, randomised wrapper class) is actuated via an image-template match (`vision.clickByImage`).
- The status flips to 'Playing'.

## Assumed

- The template `assets/play-icon.png` is a tight crop of the rendered control (font-independent, solid shape).

## Cannot / must NOT verify

- Any DOM-selector strategy — there is deliberately no stable handle; only the image path is valid.

## How to run offline

```bash
NM="$PWD/../../../../src/container/node_modules"
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```
