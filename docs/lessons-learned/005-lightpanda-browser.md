# Lessons Learned: Lightpanda Browser Integration

**Date**: 2026-03-14
**Spec**: `005-lightpanda-browser`

---

## Why This Document Exists

This documents the complete journey of integrating Lightpanda as an alternative browser engine for check_cep. Lightpanda promises 9x less memory and 11x faster execution than Chromium for headless DOM workloads. The integration itself is sound, but Lightpanda's CDP compatibility is still WIP, which limits real-world usability. Every technical constraint discovered here will save future debugging time as Lightpanda matures.

---

## The Core Constraint: No Config-Level CDP Redirect

Playwright has no config-level `connectOverCDP` option. The only way to redirect `chromium.launch()` to a CDP endpoint without modifying user test files is a CJS monkey-patch loaded via `NODE_OPTIONS=--require`. This is the same pattern used by `ts-node/register` and `dotenv/config` — standard Node.js practice.

The patch file (`patch-lightpanda.js`) is loaded only when `BROWSER=lightpanda`, keeping the default Chromium path completely untouched.

---

## Lightpanda's CDP Limitations (Nightly Build, March 2026)

### What Works

| Operation | Status |
|-----------|--------|
| `connectOverCDP('http://127.0.0.1:9222')` | Works |
| `browser.contexts()[0]` (default context) | Works |
| `context.newPage()` on default context | Works |
| `page.goto(url)` (first navigation) | Works on simple sites |
| `page.title()` | Works |
| `page.locator(sel).textContent()` | Works |
| `page.locator(sel).count()` | Works |
| `page.locator(sel).getAttribute(attr)` | Works |
| `page.locator(sel).first()` | Works |
| Multiple locator queries on the same page | Works |
| `expect(locator).toContainText(text)` | Works |

### What Crashes or Fails

| Operation | Failure Mode |
|-----------|-------------|
| `page.goto(url)` (second navigation) | `Target page, context or browser has been closed` — Lightpanda crashes |
| `page.locator(sel).fill(text)` | Crashes the CDP server |
| `page.locator(sel).click()` (when it navigates) | Navigation succeeds but connection drops immediately after |
| `browser.newContext()` | `Cannot have more than one browser context at a time` |
| `Emulation.setUserAgentOverride` CDP method | `UnknownMethod` — Playwright calls this during context/page setup |
| Complex/JS-heavy sites (e.g. mannheimer.de) | Segfault / CDP server crash during `page.goto()` |

### The Pattern

Lightpanda supports **single-navigation, read-only DOM interaction**. One `goto()`, then as many locator queries as you want. Any mutation (`fill`, `click` that navigates) or second navigation kills the server. Complex sites crash during the initial load.

See also: [lightpanda-io/browser#384](https://github.com/lightpanda-io/browser/issues/384) — segfault during CDP connection.

---

## Technical Decisions and Workarounds

### 1. Monkey-Patch Must Override `browser.newContext()`

**Problem**: Playwright's `@playwright/test` framework creates a new browser context for each test (for isolation). `browser.newContext()` triggers `Emulation.setUserAgentOverride` which Lightpanda doesn't implement, AND Lightpanda can only have one context.

**Solution**: The monkey-patch overrides `browser.newContext()` to return the default context that `connectOverCDP` provides:

```javascript
async function connectAndPatch() {
  const browser = await pw.chromium.connectOverCDP(CDP_ENDPOINT);
  const defaultContext = browser.contexts()[0];
  browser.newContext = async function(_options) {
    return defaultContext;
  };
  return browser;
}
```

This bypasses both the `UnknownMethod` error and the single-context limitation. The trade-off is no test isolation (all tests share one context), which is acceptable for Lightpanda's use case.

### 2. Lightpanda Lifecycle: Python, Not Node.js

An earlier draft proposed a `start-lightpanda.js` helper to start the CDP server. We eliminated the extra process layer — `run.py` starts the binary directly via `subprocess.Popen`, health-checks via `http://127.0.0.1:9222/json/version`, and terminates in a `try/finally`. Simpler, no Node.js process management overhead.

### 3. Binary Installation: Copy, Don't Symlink

The `@lightpanda/browser` npm package downloads the native binary to `~/.cache/lightpanda-node/lightpanda` via a postinstall script. This is a volatile cache location.

The npm package exports no `executablePath` property (it returns `undefined`). The internal code resolves the path as `process.env.LIGHTPANDA_EXECUTABLE_PATH ?? ~/.cache/lightpanda-node/lightpanda`.

**Solution**: In the Dockerfile, after `npm ci`, copy the binary to `/usr/local/bin/lightpanda`:

```dockerfile
RUN LPBIN="$HOME/.cache/lightpanda-node/lightpanda" && \
    if [ -x "$LPBIN" ]; then \
      sudo cp "$LPBIN" /usr/local/bin/lightpanda && \
      sudo chmod 755 /usr/local/bin/lightpanda; \
    fi
```

**Don't**: Symlink to the cache path (volatile). Don't use `require('@lightpanda/browser').executablePath` (returns `undefined`).

### 4. `[cep]` Log Prefix Convention Needs Two Filters

The `[cep]` prefix convention lets container infrastructure messages (monkey-patch load, CDP startup) be identified and filtered from Nagios output. But filtering happens in two places:

- **`run_playwright()` in run.py**: Filters `[cep]` lines from the subprocess stdout/stderr streams. This catches messages that go through the pipe.
- **`extract_output_from_steps()` in check_cep**: Must also filter `[cep]` lines from `steps.json` stderr entries. Playwright's JSON reporter captures `console.error()` calls per-test, so `[cep] Overriding chromium.launch...` ends up in steps.json even though `run_playwright()` filtered it from the raw stream.

Without the steps.json filter, a passing Lightpanda test produces WARNING (exit 1) instead of OK (exit 0) because `has_stderr_in_steps` is set.

### 5. Print vs Logger in Container Code

Python-side `print("[cep] ...")` calls in `main()` bypass `run_playwright()`'s filter — they go directly to the container's stdout, which the host captures as raw output. These must use `logger.debug()` instead. The `[cep]` prefix convention is only needed for JavaScript output (which arrives via the subprocess pipe and can't use Python's logger).

---

## What the Test Suite Covers

### Lightpanda-Specific Fixture

`tests/fixtures/tc_lp_pass/` — a minimal test that stays within Lightpanda's capabilities:

```typescript
test('page loads and contains expected text', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(page.locator('h1')).toContainText('Example Domain');
  await expect(page.locator('p').first()).toContainText('documentation examples');
});
```

Single navigation, multiple DOM reads, no mutations. Uses `example.com` because complex sites crash Lightpanda.

### Test Matrix

| Test | Browser | What It Validates |
|------|---------|-------------------|
| `test_local_lightpanda[tc_lp_pass]` | Lightpanda | Full stack: CDP startup, monkey-patch, goto, DOM assertions, result parsing, Nagios OK output |
| `test_local_lightpanda[tc_syntax]` | Lightpanda | Error handling: broken test file produces CRITICAL/UNKNOWN (no Lightpanda-specific behavior, but validates the pipeline) |

Existing Chromium fixtures (`tc_pass`, `tc_fail`, etc.) are NOT run with Lightpanda because they use `fill()`, `click()`, and multiple navigations.

---

## Rules for Future Work

- **Don't fight Lightpanda's limitations in the monkey-patch** — if an operation crashes the CDP server, no amount of patching will fix it. Wait for upstream support.
- **Test with `example.com`** — it's the only site guaranteed to work. Real-world sites are unpredictable with current Lightpanda builds.
- **Rebuild the container image to pick up new Lightpanda nightlies** — the `@lightpanda/browser` npm package downloads the latest nightly on `npm install`. As Lightpanda adds CDP method support, more operations will work without code changes on our side.
- **The `newContext` override is the critical workaround** — if Lightpanda adds multi-context support, this patch can be simplified but doesn't need to be removed (returning the default context is harmless).
- **Watch [lightpanda-io/browser](https://github.com/lightpanda-io/browser/issues) for CDP compatibility progress** — specifically `Emulation.setUserAgentOverride` support, multi-context support, and `fill()`/`click()` stability.
