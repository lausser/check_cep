# VERIFICATION — ConsentFirstVisit

## Verified

- The consent dialog is dismissed **only if present** (robust to appears-sometimes).
- The account report opens and shows its text.

## Assumed

- A fresh browser context starts storage-clean, so 'first visit' is deterministic.

## Cannot / must NOT verify

- Whether the dialog appears on any given run — the test must pass either way, so it is not asserted to be present.

## How to run offline

```bash
NM="$PWD/../../../../src/container/node_modules"
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```
