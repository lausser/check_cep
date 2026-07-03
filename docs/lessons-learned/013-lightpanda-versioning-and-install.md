# Lessons Learned: Lightpanda Versioning, Installation, and Container Integration

**Date**: 2026-03-22
**Topic**: Lightpanda package/binary version split, Docker installation strategy, and `check_cep` integration behavior

---

## Why This Document Exists

Lightpanda is easy to misunderstand in this repository because there are two
related but different deliverables:

1. an npm package called `@lightpanda/browser`
2. a native browser binary released from the `lightpanda-io/browser` repository

They are connected, but they are **not** versioned from the same source tree and
**do not** share the same visible version number scheme.

That leads to recurring confusion such as:

- "GitHub shows `v0.2.6`, so where did `1.2.0` come from?"
- "If `npm install` succeeds, which binary is actually being run?"
- "Is `node_modules/.bin/lightpanda` the real browser or a wrapper?"
- "Which path should be used in production: `~/.cache/...` or `/usr/local/bin/...`?"
- "How do we pin Lightpanda reproducibly in our Docker image?"

This document answers those questions concretely for `check_cep` maintainers and
future AI agents.

---

## The Short Answer

There are two version streams:

- **npm wrapper package**: `@lightpanda/browser`
  - published from `https://github.com/lightpanda-io/node-packages`
  - current published versions observed: `1.0.1`, `1.1.0`, `1.2.0`
  - npm registry `dist-tags.latest` currently points to `1.2.0`

- **native browser binary**: Lightpanda browser executable
  - released from `https://github.com/lightpanda-io/browser/releases`
  - current stable browser release observed: `v0.2.6`
  - moving channel also exists as `nightly`

These are different repositories and different version series.

So it is valid for both of these to be true at the same time:

- npm package version = `1.2.0`
- native browser release = `v0.2.6`

That is not a bug. It is their current packaging model.

---

## Where `1.2.0` Comes From

The `1.2.0` value does **not** come from the browser release page.

It comes from the npm package metadata for `@lightpanda/browser`.

Evidence:

- npm registry entry for `@lightpanda/browser` shows:
  - `dist-tags.latest = 1.2.0`
  - versions: `1.0.1`, `1.1.0`, `1.2.0`
- the installed package file also shows:
  - `src/container/node_modules/@lightpanda/browser/package.json`
  - `"version": "1.2.0"`

The package metadata points back to a different GitHub repository:

- `repository.url = https://github.com/lightpanda-io/node-packages.git#main`
- `homepage = https://github.com/lightpanda-io/node-packages/tree/main/packages/browser#readme`

That means `npm install @lightpanda/browser` is **not** pulling from the browser
release page directly. It is pulling a packaged wrapper/module published to npm
from the `node-packages` repository.

---

## Where `v0.2.6` Comes From

`v0.2.6` comes from the **native browser** release page:

- `https://github.com/lightpanda-io/browser/releases`

That page shows release assets like:

- `lightpanda-x86_64-linux`
- `lightpanda-aarch64-linux`
- etc.

This is the real browser executable.

It is what supports CLI commands such as:

- `lightpanda fetch`
- `lightpanda serve`
- `lightpanda mcp`
- `lightpanda version`

In our container design, this is the binary that should live at a stable path:

- `/usr/local/bin/lightpanda`

---

## How npm and GitHub Are Aligned

They are aligned by intent, not by sharing a single version number.

The relationship is:

- `@lightpanda/browser` is the Node.js wrapper/integration package
- the npm package's postinstall script downloads a native Lightpanda browser
  binary for the host platform
- by default, it downloads that binary into:
  - `~/.cache/lightpanda-node/lightpanda`
- the npm package also provides a CLI shim at:
  - `node_modules/.bin/lightpanda`

So the npm package is a Node-facing delivery/integration layer around the native
browser.

Important detail:

- the package and the binary are related products,
- but the package version number and the native browser release tag do not match
  one-to-one.

This is why pinning has to be handled carefully.

---

## What `npm install @lightpanda/browser` Actually Gives You

After `npm install` / `npm ci`, you typically get all of these:

1. **Node module code**
   - the JS/TS package in `node_modules/@lightpanda/browser`

2. **CLI shim**
   - `node_modules/.bin/lightpanda`
   - this is **not** the native browser binary
   - it is a Node CLI shipped by the npm package

3. **Downloaded native binary**
   - default location: `~/.cache/lightpanda-node/lightpanda`
   - downloaded by package postinstall unless overridden

4. **Programmatic API**
   - e.g. `import { lightpanda } from '@lightpanda/browser'`

That means `npm install` alone does **not** mean your production command should
be `node_modules/.bin/lightpanda`.

---

## The Shim vs the Real Binary

This is the single most confusing part.

### `node_modules/.bin/lightpanda`

This is the npm package CLI shim from `@lightpanda/browser`.

What it does:

- provides package CLI behavior such as `upgrade`
- performs or coordinates binary download logic
- may use `LIGHTPANDA_EXECUTABLE_PATH`
- is a JS wrapper, not the native browser executable itself

Observed behavior in our environment:

- `lightpanda --help` via the shim showed a minimal wrapper-style command set
- it did **not** behave like the full native browser CLI

### `~/.cache/lightpanda-node/lightpanda`

This is the downloaded native browser executable.

Observed behavior:

- after making it executable, it showed the real command set:
  - `fetch`
  - `serve`
  - `mcp`
  - `help`
- it could start the CDP server used by Playwright integration

### `/usr/local/bin/lightpanda`

This should be the stable production path inside our container.

Why:

- `.cache` is not a production runtime location
- the npm shim is not the stable command surface we want to depend on
- `run.py` already expects a stable system path:
  - `/usr/local/bin/lightpanda`

Conclusion:

- use npm package for Node integration and package metadata
- use a pinned native binary installed to `/usr/local/bin/lightpanda` for
  runtime in the container

---

## Why `.cache` Should Not Be the Runtime Contract

The npm package README explicitly mentions:

- default binary folder: `~/.cache/lightpanda-node`
- `LIGHTPANDA_EXECUTABLE_PATH` may be specified to use your own version and
  avoid the postinstall-installed binary

That means `.cache` is an implementation detail of package installation, not a
stable runtime contract.

Reasons not to rely on `.cache` in production:

- cache directories are not intended as public executable locations
- content may be replaced by package upgrade logic
- permissions may be wrong or inconsistent
- PATH should not depend on a cache directory
- debugging becomes harder because the runtime binary is hidden behind package
  installer behavior

For containerized production use, a stable path like `/usr/local/bin/lightpanda`
(or another explicit system path) is the right solution.

---

## What Broke in `check_cep`

The `check_cep` Lightpanda lane expects the real binary at:

- `src/container/image/run.py`
- command launched:
  - `['/usr/local/bin/lightpanda', 'serve', '--host', '127.0.0.1', '--port', '9222']`

That design is correct.

What can go wrong is installation drift:

- if the Dockerfile fails to copy the real binary to `/usr/local/bin/lightpanda`,
  the Lightpanda tests fail before Playwright starts
- if the image quietly depends on npm postinstall downloading a moving nightly
  binary into `~/.cache`, reproducibility is lost
- if PATH prefers `node_modules/.bin`, interactive shell usage may hit the shim
  instead of the real browser

The solution is not to weaken tests.

The solution is to make the binary install path deterministic.

---

## The Correct Container Strategy

For this repository, the robust pattern is:

1. pin the npm package version
2. pin the native browser release version separately
3. install the native binary to `/usr/local/bin/lightpanda`
4. set `LIGHTPANDA_EXECUTABLE_PATH=/usr/local/bin/lightpanda`
5. let `run.py` launch `/usr/local/bin/lightpanda` explicitly

This produces a clear contract:

- npm package is pinned and available
- runtime binary is pinned and available
- `run.py` uses the stable path directly
- interactive shell use can also rely on `/usr/local/bin/lightpanda`

---

## Why `LIGHTPANDA_EXECUTABLE_PATH` Matters

The package README says:

- `LIGHTPANDA_EXECUTABLE_PATH` can be specified if you want to use your own
  version and avoid the binary from being installed on postinstall

This is important in Docker builds.

If `npm ci` runs **before** that variable is set, the package postinstall may:

- download a binary into `~/.cache/lightpanda-node/lightpanda`
- and that binary may come from a moving `nightly` release

That silently undermines reproducibility.

So if you want a truly pinned build, set:

- `LIGHTPANDA_EXECUTABLE_PATH=/usr/local/bin/lightpanda`

**before** `npm ci`, and independently install the pinned native browser binary
into `/usr/local/bin/lightpanda` yourself.

That is the clean separation.

---

## The Version Pair We Chose Here

This repository initially pinned the pair below while the integration was still
being investigated:

- npm package: `@lightpanda/browser` `1.2.0`
- native browser binary: `v0.2.6`

Why this choice is reasonable:

- `1.2.0` is the current npm `latest` but now explicitly pinned
- `v0.2.6` is the latest stable native browser release rather than `nightly`
- this avoids silent drift in both the npm layer and the native binary layer

Important nuance:

- this pairing is a practical pinning decision,
- not a vendor-published statement that `1.2.0 == v0.2.6` semantically.

They remain distinct version streams.

### Runtime cleanup result

After tracing the actual `check_cep` Lightpanda execution path, we confirmed
that the npm package is **not** used at runtime in this repository.

Actual runtime path:

- `src/container/image/run.py` starts `/usr/local/bin/lightpanda serve ...`
- `src/container/image/patch-lightpanda.js` patches Playwright to use
  `playwright-core.chromium.connectOverCDP('http://127.0.0.1:9222')`
- user tests never import `@lightpanda/browser`

So the active runtime dependency is only:

- the standalone native Lightpanda binary installed at `/usr/local/bin/lightpanda`

The `@lightpanda/browser` package was therefore removed from
`src/container/package.json`, and the Lightpanda integration tests still passed.

This is an important simplification:

- the package is useful for Node developers in general,
- but `check_cep` does not need it for its current Playwright-over-CDP
  integration,
- which means the repository no longer needs to pin both at runtime.

Current practical state for this repo:

- standalone binary is pinned and installed explicitly
- npm wrapper package is not part of the runtime path anymore

---

## Update (spec 018): bump to `0.3.4` and the release-tag scheme change

**Date**: 2026-07-03

The native browser binary was bumped from `v0.2.6` to `0.3.4`
(`ARG LIGHTPANDA_BROWSER_VERSION` in `src/container/Dockerfile`).

**The critical gotcha — the tag scheme changed:**

- the old `0.2.x` line was tagged **with** a `v` (`v0.2.6`)
- the `0.3.x` releases are tagged **without** the `v` prefix (`0.3.4`)
- `GET /releases/tags/v0.3.4` → **404**; `GET /releases/tags/0.3.4` → **200**

So the pin MUST be `0.3.4`, **not** `v0.3.4`, or the `curl -f` binary download
in the Dockerfile 404s and the build hard-fails. The download-URL template
itself was unchanged (it already interpolates the tag verbatim).

Verify after building:

```bash
podman run --rm check_cep:test bash -lc '/usr/local/bin/lightpanda version'
# expect: 0.3.4   (v0.2.6 reported a bare commit hash instead)
```

**Capability delta observed on 0.3.4** (verified via the integration lane and a
throwaway probe fixture, cross-checked against the browser changelog — not
assumed):

- **Works now**: read-only navigation; **text/password `fill()` actually writes
  the DOM value** (confirmed via `page.evaluate`, contradicting the old 0.2.6
  "fill crashes" note); the failure/timeout verdict paths. `tc_fail` and
  `tc_timeout` were promoted into `FIXTURES_LIGHTPANDA`.
- **`locator.click()` works on SIMPLE/static pages** but **hangs on complex /
  JS-heavy pages**. Verified: an `example.com` link-click navigates on 0.3.4
  (matching the official `lightpanda-io/demo`, which clicks
  `getByText('Campfire Commerce')` on its own static demo site). But on
  `practice.expandtesting.com` the button is *found* (count = 1) yet Playwright's
  click actionability handshake never completes → timeout. That page-complexity
  boundary — not "click is broken" — is why `tc_pass` and `tc_register_pass`
  (both target that heavy site) stay Chromium-only.
- Also still limited: `fill()` on `<input type=number|date>` throws
  `InvalidStateError`; `getByText()` / `expect().toHaveValue()` matchers are
  unreliable on some pages (`getByText('More information')` matched 0 on
  `example.com`).
- Vision stays permanently Chromium-only (no rendering engine).

We did **not** weaken any check to make it pass — heavy-site interactions stay on
Chromium.

**Reconciling with the changelog and demo**: 0.2.7–0.3.4 shipped a lot (fill/click
tools, `Input.dispatchMouseEvent`, concurrent navigations, multi-page sessions),
and much of it is real — text fill and simple-page clicks genuinely work now. The
demo passes because it drives a lightweight static site. Our fixtures failed
because they drive a heavy third-party app. **Investigation lesson**: I first
concluded "fill is broken," then "click always hangs" — both wrong. Bisecting
each step in isolation (count the element, read the value back via `evaluate`,
click a confirmed element on a simple page) revealed the real, narrow boundary:
Playwright-over-CDP click actionability doesn't complete on heavy pages. Verify
per-step against the exact driver path; don't generalize from the first error
string.

---

## How to Explain This to Future Maintainers

The simplest explanation is:

> Lightpanda currently has two moving parts:
> the npm wrapper package from `lightpanda-io/node-packages` and the native
> browser binary from `lightpanda-io/browser`. Their versions do not match.
> Pin them separately.

That is the key lesson.

---

## Practical Rules for Future AI Agents

If you touch Lightpanda integration in this repo, follow these rules:

1. Do not assume the npm package version matches the browser release tag.
2. Do not use `.cache` as the production runtime path.
3. Do not rely on `node_modules/.bin/lightpanda` as the authoritative browser CLI.
4. Do install the native binary to `/usr/local/bin/lightpanda`.
5. Do verify whether the npm wrapper package is actually used before keeping it as a dependency.
6. Do pin the runtime binary explicitly.
7. Do verify the Lightpanda integration lane with real tests after changes.

---

## Verification Commands That Were Useful

### Check npm package version

```bash
npm view @lightpanda/browser version versions --json
```

### Inspect browser release assets

```bash
curl https://api.github.com/repos/lightpanda-io/browser/releases/tags/v0.2.6
```

### Check the installed native binary

```bash
podman run --rm check_cep:debug bash -lc '/usr/local/bin/lightpanda version'
```

### Verify the npm wrapper package is absent (current repository state)

```bash
podman run --rm check_cep:debug bash -lc 'node -e "try { require.resolve(\"@lightpanda/browser\"); console.log(\"present\"); } catch (e) { console.log(\"missing\"); }"'
```

### Verify the Lightpanda integration lane

```bash
CEP_IMAGE=check_cep:debug pytest tests/integration/test_modes.py -k "lightpanda" -v
```

---

## Final Takeaway

If you remember only one thing, remember this:

- `@lightpanda/browser` and `lightpanda-io/browser` are related, but they are
  not the same artifact and they are not on the same version numbering scheme.

For `check_cep` specifically, the runtime should depend on the standalone native
binary at a stable system path. Treat `~/.cache` as a package implementation
detail, not as your runtime contract.
