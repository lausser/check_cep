# Changes

Each section corresponds to a completed specification (spec). Specs are
the unit of release — when a spec is finished and merged, it becomes
available in the next container image build.

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
