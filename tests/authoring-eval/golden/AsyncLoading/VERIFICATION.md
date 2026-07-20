# VERIFICATION — AsyncLoading

## Verified

- The test waits on the balance's **state** (visibility + loaded flag), not a fixed sleep.
- The balance is captured as perfdata and confirmed > 0.

## Assumed

- The reveal delay is bounded; web-first assertions retry within the default timeout.

## Cannot / must NOT verify

- The exact load delay (randomised each run) — a fixed sleep would flake and is avoided.

## How to run offline

```bash
NM="$PWD/../../../../src/container/node_modules"
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```
