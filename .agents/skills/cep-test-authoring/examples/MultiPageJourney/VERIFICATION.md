# VERIFICATION — MultiPageJourney (flagship)

The 60-second report: what this ideal test verifies, assumes, and cannot verify.

## Verified

- The landing page has **no login form**; the actionable path starts elsewhere.
- The full journey is traversed via stable ids, not positions:
  landing → `#onlinebanking-entry` → onlinebanking → `#to-login` → login →
  fill demo credentials → **dashboard**.
- On the dashboard, the **stable** signals are asserted literally: account name
  ("Demo Checking Account") and IBAN.
- The **available balance** is read, confirmed to be a number > 0, and emitted
  as perfdata (`NagiosPerfData: 'AvailableBalance'=<number>`) — the requested
  "Value to Capture".

## Assumed

- Demo credentials `demo` / `Passw0rd!` (carried in the deployed package `.env`;
  mirrored in `sample-app/journey/.env.example`).
- The pages are opened via `file://` with relative links (self-contained, no
  server). In a deployed package the journey pages travel alongside the test.

## Cannot / must NOT verify

- The **"Last login"** timestamp is dynamic (a real clock value, different every
  visit). The test asserts only that it is present — never its literal value.
  Asserting it would make the check flap.

## How to run offline

```bash
NM="$PWD/../../../../src/container/node_modules"   # from this dir
NODE_PATH="$NM" node "$NM/.bin/playwright" test --config playwright.config.ts
```
