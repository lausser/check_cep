# VERIFICATION — AmbiguousElements

## Verified

- The generic 'Add to cart' name matches many nodes (proven with a count assertion).
- The intended Gold Credit Card button is disambiguated to exactly one node and clicked.
- The cart reflects 'gold-card'.

## Assumed

- The stable `data-product` scope is the correct disambiguator.

## Cannot / must NOT verify

- Which other products exist — only the Gold Credit Card outcome is asserted.

## How to run offline

```bash
NM="$PWD/../../../../src/container/node_modules"
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```
