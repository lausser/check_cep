# Lessons Learned: S3 Explicit TGZ Artifact Source

**Spec**: `017-s3-tgz-source`
**Date**: 2026-03-31
**Status**: Completed

---

## Why This Document Exists

Spec 017 replaced an implicit S3 key-derivation scheme (`{testname}/scripts.tgz`) with an explicit `--test-artifact=/bucket/key/archive.tgz` parameter, added local TGZ support, and refactored the container-side plugin architecture. This write-up captures the lessons from the full speckit pipeline (plan → tasks → implement), including the mid-session context handover that triggered a quality review and a targeted cleanup pass.

---

## Lesson 1: Make the Break Total — No Compatibility Shims

### What Happened

The original `source_s3.py` derived the S3 bucket and key from the test name (`{testname}/scripts.tgz`). The first implementation plan proposed extending the plugin to accept either the old scheme or the new `TEST_ARTIFACT` env var.

During task generation the approach was explicitly rejected: *"do not respect existing s3 tests, whatever their bucket/folder/file structure looked like. S3 test artifacts are always tar.gz or tgz and follow the form /bucket/whatever-folders-and-keys/testfolder.{tgz,tar.gz}"*.

### The Result

`source_s3.py` was a complete rewrite with zero fallback code. All integration tests for S3 were also rewritten from scratch. The `conftest.py` S3 helper was updated to upload `tests.tgz` with the new path format — the old `scripts.tgz` key is gone from the entire codebase.

### The Rule

**When you remove a parameter or change a contract, remove it completely.** Backward-compatibility shims accumulate and become the thing you are testing, not the real code. A clean break with a clear error message is easier to maintain and easier to test than a multi-path implementation that pretends both old and new are valid.

---

## Lesson 2: Mutual Exclusion Checks Fire at Validation Time, Not at Argparse Time

### What Happened

`run_check_cep_s3()` in `tests/integration/conftest.py` called the base `run_check_cep()` helper, which unconditionally added `--test-dir` to the command. Then `run_check_cep_s3()` added `--test-artifact` via `extra_args`. The inline comment said *"extra_args override them because argparse uses the last occurrence for store actions"*.

That was true for all other overrides. It was false for the new `--test-dir` / `--test-artifact` mutual-exclusion check, which ran during CLI validation after argparse had finished and saw both values set.

All 18 `test_s3[*]` tests failed with `UNKNOWN - --test-dir and --test-artifact are mutually exclusive`.

### The Fix

`run_check_cep()` was changed to accept `test_dir=None` and only emit `--test-dir` when the argument is not None. `run_check_cep_s3()` passes `test_dir=None`.

### The Rule

**Never rely on "last argument wins" to disable a conflicting argument.** If your validation logic can see two flags that it considers mutually exclusive, it does not matter which one was added last — it will reject both. Shared test helpers that compose CLI commands must actively suppress arguments that are inappropriate for the mode they are testing.

---

## Lesson 3: Container-Side Plugins Belong in a Shared Module, Not Duplicated

### What Happened

Both `source_local.py` and `run.py` independently defined the same set of directories to skip when walking test trees (`{"functions", "variables", "node_modules"}`). They also duplicated the same four-line `os.walk` pattern. When a new shared-utility directory type is added, both files need updating — and the risk is that one of them is missed.

### The Fix

Created `src/container/image/plugins/_shared.py` with `SKIP_DIRS` and `has_test_files()`. `run.py` adds the plugins directory to `sys.path` at module load time (it already does this for plugin loading anyway) and imports `SKIP_DIRS`. `source_local.py` imports `has_test_files` directly.

### The Rule

**If two container-side modules share a predicate or constant, extract it to `_shared.py` in the plugins directory.** The underscored name makes clear it is internal infrastructure, not a loadable plugin. `run.py` already manages the plugins path — a one-time `sys.path.insert` at module load is the correct extension point.

---

## Lesson 4: Test Factories and Module Loaders Belong in `conftest.py`, Not in Individual Test Files

### What Happened

The `importlib` boilerplate for loading `src/check_cep` (a single-file plugin that is not a proper Python package) was copy-pasted into three files:
- `tests/unit/test_run_context.py`
- `tests/unit/test_cleanup.py`
- `tests/integration/conftest.py`

The `make_config()` / `make_ctx()` test factories lived only in `test_run_context.py`. When `test_cleanup.py` needed them, the import was written as `from tests.unit.test_run_context import make_ctx, make_config` — which fails because `tests` is not a package — and then worked around with a fragile `sys.path.insert(0, str(Path(__file__).parent))`.

### The Fix

Created `tests/unit/conftest.py` as the single source of truth for unit tests:
- One `importlib` loading block
- One `sys.path.insert` for the container plugins directory
- `make_config()` and `make_ctx()` defined here, imported by the test files that need them

The importlib boilerplate and factory definitions were removed from `test_run_context.py` and `test_cleanup.py`. The `sys.path` hack in `test_cleanup.py` was removed entirely.

### The Rule

**Pytest processes `conftest.py` before any test file in its directory and adds the conftest directory to `sys.path`.** This makes `from conftest import X` work without any path manipulation. Shared test infrastructure — module loaders, factories, helpers — belongs in `conftest.py`, not scattered across individual test modules. Cross-module imports between test files (`from test_X import Y`) are a code smell; the shared thing should be in conftest.

---

## Lesson 5: Protocol Parameters That Are Genuinely Unused Should Be Named with a Leading Underscore

### What Happened

Both `source_s3.acquire_tests()` and `source_local.acquire_tests()` receive a `test_name` parameter required by the `TestSourcePlugin` protocol. In these two implementations the parameter is unused — the artifact path comes from the `TEST_ARTIFACT` environment variable. The docstrings said "Unused" but the parameter name suggested it was meaningful.

### The Fix

Renamed to `_test_name` in both plugins. The underscore prefix is the Python convention for *"this parameter is required by the interface but intentionally not used in this implementation"*.

### The Rule

**Use `_name` for interface-required parameters that are intentionally unused.** It silences linter warnings, signals intent to readers, and prevents future maintainers from wiring up the parameter under the impression that it was simply forgotten.

---

## Lesson 6: Section Headers in Long Single-File Plugins Should Use Functional Names

### What Happened

`src/check_cep` is a 1758-line single-file plugin (deploy-without-install architecture). Its section headers accumulated spec and task references during development: `# Podman command building (T008)`, `# Run context (010-run-context)`, `# CgroupPoller (T027-T031)`.

These references were meaningful during construction but become noise for any reader not involved in the original development. They create a false impression that the code structure maps to an external ticketing system.

### The Fix

All 14 section headers with task or spec IDs were replaced with pure functional descriptions: `# Podman command construction`, `# Run configuration and context`, `# Cgroup resource monitoring`.

### The Rule

**Production code comments should explain what and why, not how it was tracked.** Spec and task IDs belong in commit messages and changelogs, not in function-level section headers. A reader navigating `src/check_cep` should be able to orient themselves from the headers alone, without access to the original task board.

---

## DO

- **DO** make API breaks total — no compatibility shims, clean rewrite, clear error on the old path.
- **DO** put all shared test infrastructure (module loaders, factories, path setup) in `conftest.py`.
- **DO** use `_name` for protocol-required parameters that are intentionally unused.
- **DO** extract shared constants and predicates into a `_shared.py` module rather than copy-pasting.
- **DO** write integration tests that cover the new format end-to-end, including cache hit on second run.
- **DO** update `conftest.py` S3 helpers alongside the code change — the helper is part of the tested surface.

## DON'T

- **DON'T** rely on argparse "last argument wins" to suppress a conflicting flag — mutual exclusion checks see all values regardless of order.
- **DON'T** cross-import between test files (`from test_X import Y`) — use `conftest.py` instead.
- **DON'T** leave task or spec IDs in section headers in production code — they are meaningless without the task board.
- **DON'T** preserve old key-derivation logic as a fallback when the intent is a clean protocol change.
- **DON'T** duplicate skip-dir sets or walk predicates across modules — any future change will be applied inconsistently.
