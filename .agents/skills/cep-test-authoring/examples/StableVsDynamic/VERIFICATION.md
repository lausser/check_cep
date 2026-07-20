# VERIFICATION — StableVsDynamic

## Verified

- The fixed account number is asserted literally.
- The balance is captured as perfdata and confirmed > 0.

## Assumed

- The account number is genuinely stable across runs.

## Cannot / must NOT verify

- The session clock is dynamic (ticks every second) — it is present but NEVER asserted for a specific value.

## How to run offline

```bash
NM="$PWD/../../../../src/container/node_modules"
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```
