# VERIFICATION — Iframe

## Verified

- The test enters the same-origin frame (`frameLocator('#widget')`) to click and read.
- The widget confirms the €25.00 payment.

## Assumed

- The pages are HTTP-served (webServer) so parent and frame share a real origin (research R7).

## Cannot / must NOT verify

- Targeting the top document — the button lives only inside the iframe.

## How to run offline

```bash
NM="$PWD/../../../../src/container/node_modules"
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```
