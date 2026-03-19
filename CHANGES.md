# Changes

Each section corresponds to a completed specification (spec). Specs are
the unit of release — when a spec is finished and merged, it becomes
available in the next container image build.

---

## Spec 011 — Externalize Demo Configurations

**Branch**: `011-externalize-demo-configs`

### Summary

Moved inline demo file content out of `setup-omd-site.sh` into a new `omd-demo/` directory that mirrors the OMD site root. The setup script now does a recursive copy instead of generating files via heredocs.

### Changes

- New `omd-demo/etc/` tree containing the demo Playwright test (`consol.test.ts`, `playwright.config.ts`) and a Naemon monitoring config (`cep-demo.cfg`) with portable `$USER2$`/`$USER4$` macros.
- `setup-omd-site.sh`: replaced heredoc section with `cp -r omd-demo/etc/ $OMD_ROOT/etc/`, added validation for missing/empty `omd-demo/`, extended `chown` scope for the Naemon config path, added web symlink (`var/www/check_cep` → `var/tmp/check_cep`).

---

## Spec 010 — RunContext: Shared Execution Context

**Branch**: `010-run-context`

### Summary

Introduced two frozen dataclasses to eliminate function signature churn across the plugin:

- **`RunConfig`** (33 typed fields): immutable wrapper for all CLI arguments, replacing raw `argparse.Namespace` access after argument parsing.
- **`RunContext`** (12 fields): immutable per-run state combining identity (`hostname`, `servicedescription`, `testname`, `testident`, `container_name`), timing (`start_time`, `started_str`, `timeout_deadline`), paths (`result_dir`, `pid_file`, `omd_root`), and the nested `RunConfig`.

### Migrated Functions

Four functions now accept `RunContext` instead of individual shared-state parameters. `resolve_path_template` remains a standalone string utility (no RunContext dependency).

| Function | Before | After |
|---|---|---|
| `resolve_report_url` | 7 args | 2 args (`ctx`, `timestamp`) |
| `build_podman_command` | 5 args | 3 args |
| `run_cleanup` | 5 args | 2 args |
| `build_env_vars` | 2 args | 1 arg |
| `resolve_path_template` | 4 args | 4 args (unchanged, pure string utility) |

Total positional parameters reduced from 23 to 12.

### Other Changes

- All `args.*` access is now confined to the `RunConfig` constructor; the rest of `main()` reads from `config.*` or `ctx.*`.
- `RunContext` is logged at `DEBUG` level immediately after construction.
- `main()` is structured in four clearly separated phases: parse + `RunConfig`, validate, `RunContext` construction, run + format.
- New test helper module `tests/unit/test_run_context.py` with `make_config(**overrides)` and `make_ctx(**overrides)` factories for single-override unit test setup.
- Deleted `docs/CONTEXT.md` (superseded by `specs/010-run-context/`).

---

## Spec 009 — Local Report Housekeeping

**Branch**: `009-report-management`

### Added
- `%t` placeholder in `--result-dir` and `--report-url` — resolves to the process start time (Unix epoch), giving each run its own isolated timestamped directory
- `--report-retention Xh` — auto-deletes old per-run directories after each check, oldest-first, with a 10 s safety margin before the plugin timeout deadline
- `CleanupResult` dataclass, `ReportCleanupPlugin` Protocol, and `LocalCleanup` implementation — storage-agnostic cleanup with S3 extensibility in mind
- `CEP_STARTED` env var — host process start time passed into the container so `test-meta.json` records the same timestamp used for `%t`
- `docs/CONTEXT.md` — design document for a future `RunContext` refactor

### Changed
- `test-meta.json` schema v2: `timestamp` field renamed to `finished`; new `started` field added (Unix epoch of host process start)
- PID file relocated from `result_dir/` to `$OMD_ROOT/var/tmp/check_cep.{testident}.pid` so the duplicate-run guard works when `%t` creates unique per-run directories
- Dockerfile: direct nightly binary fallback for Lightpanda when the npm postinstall fails due to GitHub API rate-limiting during the build
- `patch-lightpanda.js`: infrastructure log lines moved from `console.error` to `console.log` with `[CEPDBG]` prefix — prevents false WARNING triggers from stderr detection
- `run.py`: `OSError` added alongside `RuntimeError` when catching Lightpanda startup failures — missing binary now produces `UNKNOWN` instead of an unhandled exception crash

### Fixed
- Playwright report URL in plugin output now resolves `%t` to the correct run timestamp when `test-meta.json` contains `started`

---

## Spec 008 — Unified Debug Logging

**Branch**: `008-debug-logging`

### Added
- `cepDebug(message)` function in `check-cep-helpers` — test authors can emit debug-only messages with the `[CEPDBG]` prefix, visible only with `--debug`
- TypeScript declaration for `cepDebug` in `check-cep-helpers/index.d.ts`

### Changed
- Vision traces (`check-cep-vision`) moved from `console.error('[cep] ...')` on stderr to `console.log('[CEPDBG] ...')` on stdout — eliminates false WARNING triggers from stderr pollution and makes vision diagnostics visible with `--debug`
- `extract_output_from_steps()` now accepts a `debug` parameter; stdout lines starting with `[CEPDBG]` are filtered out unless `--debug` is active — single filtering point on the host side
- `extract_output_from_steps()` no longer filters `[cep] ` from stderr — all stderr entries pass through unconditionally (no `[cep]` lines will be produced anymore)
- `run.py` dispatcher now forwards Playwright stdout and stderr unchanged — removed `[cep]` prefix filter loop

### Fixed
- False WARNING status when running vision-using tests (caused by `[cep]` lines on stderr being detected as `has_stderr`)

---

## Spec 007 — Vision Autoscroll (Best-Effort Interaction Functions)

**Branch**: `007-vision-autoscroll`

### Added
- `vision.clickBestEffort(locator, options?)` — scroll into view + click with progressive fallback (standard → forced → DOM-level)
- `vision.typeBestEffort(locator, text, options?)` — scroll into view + type with progressive fallback
- `vision.fillBestEffort(locator, value, options?)` — scroll into view + fill with progressive fallback
- `scrollIntoView` option (default: `true`) to opt out of automatic scrolling when needed
- Transparent Lightpanda compatibility: scroll step silently skipped on DOM-only browsers
- Debug logging for individual fallback steps when `--debug` is active (`process.env.DEBUG`)
- TypeScript declarations for all three new functions and the `scrollIntoView` option
- `check-cep-helpers` npm package bundled in the container — shared test utilities (`cepLog`, `cepLogLocated`, `cepLogFound`, `cepLogType`, `cepLogPress`, `cepLogWait`, `cepLogUrl`) for timestamped Playwright test logging

### Changed
- Existing migrated testcases refactored to use centralized bestEffort functions, replacing duplicated local `clickWithFallback` helpers and ad-hoc `scrollIntoView` evaluate calls
- Logging helpers extracted from 7 testcase-local `functions/index.ts` files into `check-cep-helpers`, eliminating identical copies of `cepLog` and its derivatives

---

## Spec 006 — README Visual Teaser

**Branch**: `006-readme-teaser`

### Added
- 4-scene animated GIF teaser at the top of README.md: passing test, Playwright report, failing test with "Invalid credentials", error details
- Title cards (1-second, dark background, white text) between each scene for context
- `scripts/teaser/teaser-pass.test.ts` — passing login with `highlightLocator()` on the "Signed in as operator" result
- `scripts/teaser/teaser-fail.test.ts` — login with "operator " (trailing space) triggers "Invalid credentials" rejection with red styling
- `scripts/teaser/record-report.js` — records Playwright HTML report navigation inside the container
- `scripts/generate-teaser.sh` — orchestrates 4 test/report recordings, title cards, video concatenation, and GIF conversion
- `make teaser` target to regenerate the GIF reproducibly

### Changed
- Login fixture (`login.html`) `handleSignIn()` now validates the username — non-"operator" usernames show "Invalid credentials" in red with light-red input backgrounds
- Pass/fail scenes are visually distinct: green "Signed in as operator" vs. red "Invalid credentials" with red-tinted input fields

### How it works
- Runs two teaser-specific tests via check_cep with Playwright video recording (`CEP_SLOW_MO=600`, `CEP_VISION_HIGHLIGHT_MS=800`)
- Passing test enters "operator" → success. Failing test enters "operator " (trailing space) → web app rejection with red error styling
- Records Playwright HTML report navigation via `podman run` with `record-report.js`
- ffmpeg generates title cards, normalizes all video segments, concatenates, and converts to GIF via two-pass palette method
- GIF parameters: 640px wide, 10 fps, 128 colors, bayer dithering — stays under 5 MB

---

## Spec 005 — Lightpanda Browser Integration

**Branch**: `005-lightpanda-browser`

### Added
- `--browser lightpanda` CLI flag for using Lightpanda as an alternative headless browser engine
- CJS monkey-patch (`patch-lightpanda.js`) that transparently redirects Playwright's `chromium.launch()` to Lightpanda's CDP endpoint — no test file changes needed
- `canScreenshot()` guard in check-cep-vision so vision functions degrade gracefully on browsers without a rendering engine
- Lightpanda integration tests (`tc_lp_pass` fixture)
- Lightpanda section in WRITING-TESTS.md

### Fixed
- `[cep]` infrastructure messages (from monkey-patch `console.error()`) no longer leak into Nagios output — filtered in both `run_playwright()` and `extract_output_from_steps()`
- Container-side `print("[cep] ...")` calls replaced with `logger.debug()` to avoid bypassing the output filter
- Lightpanda lifecycle extracted into `start_lightpanda_cdp()` / `stop_lightpanda_cdp()` helpers
- `BROWSER` env var now always set in container environment (was conditional, causing inconsistency)

### Limitations
- Lightpanda is experimental: single navigation + DOM reads only
- `fill()`, `click()` with navigation, second `goto()`, and complex sites crash the CDP server
- Vision matching not available (no rendering engine)

---

## Spec 004 — Advanced Vision Tests and Documentation

**Branch**: `004-vision-advanced-tests`

### Added
- Three worked example fixtures: `tc_vision_example_form`, `tc_vision_example_console`, `tc_vision_example_login`
- Spectate mode (`CEP_SPECTATE=1`) for headed test demos with configurable slow-motion and highlight overlays
- `WRITING-TESTS.md` — comprehensive test authoring handbook covering folder structure, vision API, templates, regions, click offsets, selector strategy, and worked examples
- Chrome binary wrapper that injects GPU-disable and Wayland flags at the binary level — `playwright codegen` now works in containers
- `cep_codegen` convenience alias for `npx playwright codegen`
- `test.step()` performance data extraction — each step's duration becomes a separate Nagios metric
- DOM selector strategy guide (recommended default over vision)

### Changed
- Tutorial moved from standalone file to `README.md`

---

## Spec 003 — check-cep-vision Library

**Branch**: `003-check-cep-vision`

### Added
- `check-cep-vision` npm package bundled in the container at `/home/pwuser/node_modules/check-cep-vision`
- Vision-only functions: `locateByImage`, `waitForImage`, `existsByImage`, `clickByImage`, `typeByImage`
- DOM helper functions: `clickFirstVisible`, `fillFirstVisible`
- Hybrid functions with automatic DOM fallback: `clickByImageOr`, `typeByImageOr`
- Debug functions: `highlightByImage`, `highlightLocator`, `highlightFirstVisible`
- Region presets (`header`, `main`, `footer`, `left`, `right`, `topLeft`, `topRight`) and custom `RectRegion` support
- Multi-scale template matching (default scales: 0.97, 1.0, 1.03)
- Ambiguity detection with configurable gap threshold
- Debug artifact output (`*-region.png`, `*-annotated.png`, `*-meta.json`)
- `--headed` flag for running tests with a visible browser on the host desktop
- TypeScript declarations (`index.d.ts`) for full IDE support

### Dependencies
- `opencv-wasm` 4.3.0-10 (WASM-compiled OpenCV for template matching)
- `pngjs` 7.0.0 (PNG decode/encode)

---

## Spec 002 — Test Environment and Bug Fixes

**Branch**: `002-test-env-setup`

### Added
- Pytest integration test suite (`tests/integration/test_modes.py`) with parametrized fixtures for local and S3 modes
- `conftest.py` test helpers: `run_check_cep()`, `local_test_dir()`, `run_check_cep_s3()`
- OMD install script for development environments
- Test fixtures: `tc_pass`, `tc_fail`, `tc_timeout`, `tc_syntax`, `tc_register_pass`

### Fixed
- `result_dest == "local"` guards that prevented result artefacts from being written in local mode
- Test directory discovery (`chdir` to first `test.ts` location)
- Container build setup reorganized for reproducibility

---

## Spec 001 — CEP Framework Overview

**Branch**: `001-cep-framework-overview`

### Added
- `check_cep` host-side Nagios/Naemon plugin (Python) — CLI params, Podman container orchestration, result parsing, Nagios-formatted output
- `run.py` container-side dispatcher — plugin architecture with source/dest/logging modules
- Plugin modules: `source_local.py`, `source_s3.py`, `dest_local.py`, `dest_s3.py`, `logging_loki.py`
- Container image based on Microsoft Playwright (`mcr.microsoft.com/playwright`)
- `steps.json` and `test-meta.json` result format
- CLI flags: `--test-source`, `--result-dest`, `--logging`, `--timeout`, `--host-name`, `--service-description`, `--image`, `--test-dir`, `--result-dir`
- Template variables `%h` / `%s` for host-name/service-description in paths
- SELinux-compatible volume mounts (`:z` suffix)
- CPU limit hardcoded at 2 cores
- PID file concurrency control
