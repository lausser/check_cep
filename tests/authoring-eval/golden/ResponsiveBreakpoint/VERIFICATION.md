# VERIFICATION — ResponsiveBreakpoint

## Verified

- At the pinned 1280×720 viewport the desktop 'Transfer money' CTA is visible.
- Clicking it starts the transfer.

## Assumed

- The check always runs at the standard desktop viewport (guards the 020 exploration/run viewport-alignment fix).

## Cannot / must NOT verify

- The mobile hamburger layout — out of scope at the desktop viewport.

## How to run offline

```bash
NM="$PWD/../../../../src/container/node_modules"
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```
