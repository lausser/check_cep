<!--
Sync Impact Report (2026-10-26, spec 023)
- Version change: 2.0.0 → 2.1.0 (MINOR: material expansion)
- Amended principles:
  - II. Container as Test Executor — the container no longer passes
    Playwright's exit code through; it follows the exit-code protocol
  - III. Monitoring Compatibility — added "Status classification":
    CRITICAL only for Playwright-reported failures; WARNING only for
    passed tests with an author-signalled warning; report `errors` in
    a passed run → CRITICAL; podman 125/126/127,
    container exit 3, OOM kill and unexpected codes → UNKNOWN
    (modeled on check_dopla)
  - IV. Container I/O Contract — "Exit code MUST reflect Playwright's
    test result" replaced by the exit-code protocol 0 / 1 / 2 / 3 +
    CEPUNKNOWN marker (1 = WARNING: visible stderr in the report or
    Playwright exit 150, as in check_dopla)
- Unchanged principles: I, V
- Templates requiring updates: none (plan/spec/tasks templates
  compatible)
- Follow-up TODOs: spec 023 T004 applies the remaining Principle IV
  changes (layers, merged test tree, run modes) as 2.2.0

Previous report (2026-03-04)
- Version change: 1.0.0 → 2.0.0
- Amended principles:
  - I. Separation of Concerns — added pluggable module exception
  - II. Container Determinism — replaced with Container as Test Executor,
    network access required for E2E tests
  - IV. Minimal Container Contract — expanded I/O contract to match CEP
    architecture (/tests, /results, conditional mounts, plugin modules)
  - V. Security by Default — credentials permitted for explicitly-selected
    plugins, network access required
- Unchanged principles:
  - III. Monitoring Compatibility
- Added sections: None
- Removed sections: None
- Templates requiring updates:
  - .specify/templates/plan-template.md — ✅ compatible
  - .specify/templates/spec-template.md — ✅ compatible
  - .specify/templates/tasks-template.md — ✅ compatible
- Follow-up TODOs: None
-->

# check_cep Constitution

## Core Principles

### I. Separation of Concerns

The `check_cep` host-side plugin MUST handle CLI argument parsing,
container lifecycle management (start, wait, cleanup), result
evaluation, and Nagios output formatting. The container-side
`run.py` MUST be a thin dispatcher that delegates to pluggable
Python modules for test acquisition, result delivery, and log
shipping. Each plugin module (e.g. `source_local.py`,
`dest_s3.py`, `logging_loki.py`) MUST own its concern end-to-end
as a separate file with no cross-plugin dependencies.

Transport logic (S3 downloads/uploads, Loki shipping) MAY reside
inside the container when it operates on artefacts already present
in the container filesystem. Moving these operations to the host
side would require an extra copy step and defeat the plugin
separation goal.

**Rationale**: Clean separation between host orchestration and
container-side plugin dispatch keeps each component focused and
independently testable. Plugin modules are isolated files that
can be developed, tested, and replaced without touching `run.py`
or `check_cep`.

### II. Container as Test Executor

The container MUST run with full network access so that Playwright
E2E tests can reach the target web applications under test. This is
the fundamental purpose of CEP — monitoring real web applications.

The container MUST:

- Execute `npx playwright test` against the test files in `/tests`.
- Write structured results to `/results`.
- Translate the run's outcome into the container exit-code protocol
  (Principle IV). Playwright's raw exit code (from `npx playwright
  test`, the `timeout` wrapper or a signal) MUST NOT be passed through
  unchanged.
- Minimise non-Playwright side effects (no persistent state beyond
  `/results` and `/testscripts-cache`).

Plugin modules inside the container MAY perform network operations
(S3 downloads, S3 uploads, Loki shipping) when explicitly selected
by the operator via CLI flags. When using `--test-source local` and
`--result-dest local` (the defaults), no network operations occur
beyond the Playwright tests themselves.

**Rationale**: E2E browser tests must reach the target web
applications — `--network=none` would make the tool useless.
Network-dependent plugin operations (S3, Loki) are opt-in and
only active when the operator explicitly configures them.

### III. Monitoring Compatibility

All plugin output MUST conform to the Nagios plugin development
guidelines:

- Exit codes: 0 (OK), 1 (WARNING), 2 (CRITICAL), 3 (UNKNOWN).
- First line of stdout: `STATUS - summary | perfdata`.
- Performance data MUST use standard Nagios perfdata format with
  units (e.g., `step_login=1.23s;;;`).
- Multi-line output permitted after the first line for long output.
- stderr is reserved for debug/log information only.

**Status classification**: The host plugin MUST derive the Nagios
status from every exit code it can observe — the container's
protocol code (Principle IV), the container runtime's own codes and
the cgroup state — and never pass any of them through unchanged.
CRITICAL is reserved for failures reported by the Playwright tests
themselves (failed test, test timeout, a test or config file
Playwright cannot load, or an `errors` entry in the Playwright
report of an otherwise passed run). WARNING is reserved for passed tests whose
author signalled a warning (protocol code 1, Principle IV); the host
applies the same visible-stderr rule to the report independently.
Every case in which the tests could not
run properly MUST be UNKNOWN:

- container runtime failures (podman exit 125/126/127: image
  missing, registry authentication, the command could not be
  invoked), reported with the runtime's `Error:` line;
- container-side failures (exit 3: test acquisition, merge, no
  tests found, plugin or browser start failures);
- an OOM kill (the memory limit is infrastructure);
- any exit code outside the documented protocol, reported as
  "ended with unexpected exit code N on host H".

Each branch of this classification MUST be covered by unit tests.
The mapping follows the production-proven sibling plugin
check_dopla (`PODMAN_FAILURE_CODES`, `_determine_exit_code`), whose
codes were learned from real-life failures; deviations from it
MUST be stated explicitly (deliberate deviation: OOM is UNKNOWN,
not CRITICAL).

**Rationale**: The plugin runs within Naemon/Nagios and MUST
integrate seamlessly. Non-compliant output breaks alerting,
dashboards, and performance graphing. CRITICAL notifications go to
the owners of the monitored application, UNKNOWN goes to
monitoring operations; infrastructure failures MUST NOT page
application owners for problems they cannot fix.

### IV. Container I/O Contract

The container boundary MUST follow a documented contract. Volume
mounts are conditional on the active plugin mode:

**Mounts (conditional)**:
- `/tests` — test scripts directory. Three cases:
  1. `--test-source=local` + directory artifact: host directory mounted
     directly at `/home/pwuser/tests` (ro).
  2. `--test-source=local` + `.tgz`/`.tar.gz` artifact: archive mounted
     at `/home/pwuser/input-artifact.tgz` (ro); `/tests` NOT pre-mounted —
     `source_local.py` extracts the archive to `/home/pwuser/tests` at
     container startup.
  3. `--test-source=s3`: neither `/tests` nor the archive is pre-mounted —
     `source_s3.py` downloads from S3 into the `testscripts-cache` volume
     and extracts to `/home/pwuser/tests` at container startup.
- `/results` — results output directory. Host-mounted (rw) when
  `--result-dest=local`; container-internal when `--result-dest=s3`.
- `/testscripts-cache` — S3 test script cache. Host-mounted (rw)
  when `--test-source=s3` only.

**Output files** (written to `/results`):
- `steps.json` — Playwright JSON reporter output.
- `test-meta.json` — runtime metadata (v2 schema): `started`
  (Unix epoch of host process start, from `CEP_STARTED` env var),
  `finished` (Unix epoch at write time), hostname, service,
  exit code, duration, probe location, status.
- `playwright-report/` — HTML report directory.
- `screenshots/` — failure screenshots.

**Environment variables**: Configuration from `check_cep` is passed
via `--env` flags (plugin selectors, Nagios identifiers, timeout,
plugin-specific credentials when applicable). Key variables:
- `CEP_STARTED` — Unix epoch integer string of the host-side
  `check_cep` process start time. Used by `run.py` to populate
  `test-meta.json["started"]` and to identify the run directory
  when `%t` is used in `--result-dir`.

**Exit-code protocol**: `run.py` MUST normalize its exit code to
exactly one of:
- `0` — all tests passed;
- `1` — all tests passed, but the test author signalled a warning:
  the Playwright report contains a `stderr` entry with visible
  content (e.g. `console.error()` in a test; empty entries do not
  count), or the Playwright process exited 150;
- `2` — Playwright reported a failure or the run timed out (the
  `timeout` wrapper's 124/137 and Playwright's other non-zero codes
  map to 2);
- `3` — the tests could not run properly; `run.py` prints
  `CEPUNKNOWN [[[<message>]]]` on stdout before exiting.

The host maps this protocol and the runtime's own codes to a
Nagios status per Principle III (Status classification).

Changes to this contract MUST be reviewed before implementation.

**Rationale**: A well-defined, documented contract keeps the host
and container sides decoupled. Conditional mounts reduce attack
surface when S3 plugins handle transport internally.

### V. Security by Default

All container executions MUST apply the principle of least
privilege within the constraints of E2E browser testing:

- Container MUST run as a non-root user (`pwuser`).
- Container filesystem SHOULD be read-only where feasible.
- Credentials (S3, Loki) MUST only be passed into the container
  when the operator explicitly selects a plugin that requires
  them. The default configuration (`--test-source local`,
  `--result-dest local`, `--logging none`) passes no credentials.
- Host-side file permissions MUST restrict artifact directories
  to the monitoring site user.
- Resource limits (memory, CPU) MUST be enforced via cgroups.

**Rationale**: The container executes third-party test code and
must reach external web applications, so `--network=none` is not
feasible. Defense in depth is maintained through non-root
execution, resource limits, OOM kill detection, and credentials
only present when explicitly configured.

## Technical Constraints

- **Runtime**: Python 3 for both the host plugin and container
  orchestration.
- **Container Engine**: Podman or Docker (rootless preferred).
- **Playwright**: Installed inside the container via npm; version
  pinned in `package-lock.json`.
- **Monitoring Platform**: OMD (Open Monitoring Distribution) with
  Naemon core.
- **Host OS**: Linux (RHEL/Fedora family expected, but not
  mandated).
- **Test archive format**: `.tgz` (gzip-compressed tar) for S3
  transport (`source_s3.py`). Local test source uses a directory.

## Development Workflow

- All changes to the container contract (Principle IV) MUST be
  reviewed and approved before implementation.
- Host plugin and container MUST be testable independently:
  the host plugin MUST be testable with a mock container, and
  the container MUST be testable with mock inputs (directory
  or archive depending on test-source plugin).
- Code that touches exit-code interpretation or perfdata formatting
  MUST include test coverage verifying Nagios compatibility
  (Principle III).
- Refactoring MUST NOT change the plugin's external interface
  (command-line arguments, exit codes, output format) without
  a constitution amendment.

## Governance

This constitution is the authoritative reference for architectural
decisions in the check_cep project. All code reviews and design
proposals MUST verify compliance with the principles above.

**Amendment process**:
1. Propose the change with rationale in a pull request modifying
   this file.
2. Document which principles are affected and why.
3. Update the version number per semantic versioning (below).
4. Obtain approval from at least one project maintainer.

**Version policy**:
- MAJOR: Principle removed or redefined incompatibly.
- MINOR: New principle or section added, material expansion.
- PATCH: Wording clarifications, typo fixes, non-semantic changes.

**Compliance review**: Every pull request SHOULD include a brief
note confirming which principles were considered and how compliance
was ensured.

**Version**: 2.1.0 | **Ratified**: 2026-03-02 | **Last Amended**: 2026-10-26
