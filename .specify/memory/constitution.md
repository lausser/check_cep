<!--
Sync Impact Report (2026-10-27, spec 024)
- Version change: 2.2.1 → 2.3.0 (MINOR: material expansion of the
  container I/O contract and the Playwright pinning rule)
- Amended principles:
  - IV. Container I/O Contract — output files: `test-meta.json` gains
    `versions` (`plugin`, `image`, `playwright`; each `"unknown"` when
    not determinable); environment: the host passes
    `CEP_PLUGIN_VERSION` (reserved name)
  - Technical Constraints — Playwright: version and base-image digest
    defined once in `src/container/versions.env`; `package.json` pins
    exactly; `package-lock.json` is a committed derivation; builds fail
    on disagreement (replaces "version pinned in package-lock.json")
- Templates requiring updates: none
- Approval: PENDING (maintainer)
- Follow-up TODOs: none

Previous report (2026-10-26, spec 023, amendment 3)
- Version change: 2.2.0 → 2.2.1 (PATCH: container paths spelled as in
  the code — `/home/pwuser/results`, `/home/pwuser/testscripts-cache`;
  no semantic change)
- Amended principles: II, IV (wording only)
- Templates requiring updates: none
- Approval: Gerhard Lausser (maintainer), 2026-10-26 21:05 CET
- Follow-up TODOs: none

Previous report (2026-10-26, spec 023, amendment 2)
- Version change: 2.1.0 → 2.2.0 (MINOR: material expansion, clarified
  responsibilities; no principle removed)
- Amended principles:
  - I. Separation of Concerns — explicit split of responsibilities between
    host and run.py (resolves "result evaluation" vs. the exit-code
    protocol); "thin dispatcher" replaced by a defined scope; shared helper
    modules (`_*.py`) legitimized
  - II. Container as Test Executor — tests run in the merged test tree
  - III. Monitoring Compatibility — second check_dopla deviation stated
    (report errors win over WARNING)
  - IV. Container I/O Contract — layers mounted read-only, writable merged
    test tree, run modes, `--prepare-only` entry mode, acquisition time
    budget, environment composition and delivery, `layers` in
    test-meta.json, crash safety of the exit-code protocol
  - V. Security by Default — read-only sources vs. writable merged tree;
    operator-supplied variables and secret hygiene
  - Technical Constraints — local archives; Development Workflow — the
    interface rule applies to every change, not only refactorings
- Templates requiring updates: none
- Approval: Gerhard Lausser (maintainer), 2026-10-26 20:32 CET; this
  approval also covers 2.1.0
- Follow-up TODOs: none

Previous report (2026-10-26, spec 023, amendment 1)
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
- Follow-up TODOs: completed by 2.2.0

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

The `check_cep` host-side plugin MUST handle CLI argument parsing
and validation (everything that can be checked before a container
starts), container lifecycle management (start, wait, cleanup),
the Nagios status classification (Principle III) and Nagios output
formatting.

The container-side `run.py` MUST orchestrate exactly these steps:
prepare the merged test tree (through the selected source plugin),
determine the run mode, run Playwright, translate the outcome into
the exit-code protocol (Principle IV, including the report-based
rules that protocol names), write `test-meta.json`, and hand results
and logs to the delivery and logging plugins. `run.py` MUST NOT
contain transport logic and MUST NOT format Nagios output.

Each plugin module (e.g. `source_local.py`, `dest_s3.py`,
`logging_loki.py`) MUST own its concern end-to-end as a separate
file with no dependency on another plugin. Shared helper modules
(file name starting with `_`, e.g. `_shared.py`, `_layers.py`) MAY be
imported by plugins and by `run.py`; they MUST NOT import a plugin
and MUST NOT be selectable as a plugin.

Transport logic (S3 downloads/uploads, Loki shipping) MAY reside
inside the container when it operates on artefacts already present
in the container filesystem. Moving these operations to the host
side would require an extra copy step and defeat the plugin
separation goal.

**Rationale**: Clean separation between host orchestration and
container-side plugin dispatch keeps each component focused and
independently testable. The container knows the test run, the host
knows the monitoring semantics: the container reports *what happened*
as a protocol code, the host decides *what it means* for Nagios.
Plugin modules are isolated files that can be developed, tested, and
replaced without touching `run.py` or `check_cep`, as long as they
satisfy the shared plugin protocol.

### II. Container as Test Executor

The container MUST run with full network access so that Playwright
E2E tests can reach the target web applications under test. This is
the fundamental purpose of CEP — monitoring real web applications.

The container MUST:

- Execute `npx playwright test` in the merged test tree
  `/home/pwuser/tests`, following the run mode (Principle IV).
- Write structured results to `/home/pwuser/results`.
- Translate the run's outcome into the container exit-code protocol
  (Principle IV). Playwright's raw exit code (from `npx playwright
  test`, the `timeout` wrapper or a signal) MUST NOT be passed through
  unchanged.
- Minimise non-Playwright side effects (no persistent state beyond
  `/home/pwuser/results` and `/home/pwuser/testscripts-cache`).

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
MUST be stated explicitly. Deliberate deviations: (1) an OOM kill
is UNKNOWN, not CRITICAL; (2) an `errors` entry in the report of a
passed run is CRITICAL even when a visible-stderr WARNING was
already determined (check_dopla only escalates while the status is
still OK).

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
- `/home/pwuser/layers/NN[.tgz]` — test **layers**
  (`--test-source=local`): each `--test-artifact` (directory or
  `.tgz`/`.tar.gz`), mounted **read-only**, `NN` = position on the
  command line. Layer sources are never writable and never modified
  by a run.
- `/home/pwuser/tests` — the **merged test tree**: built per run inside
  the container by the active source plugin (all local layers merged
  in order, a later layer wins; or the single S3 archive), **writable**,
  discarded with the container. It is never bind-mounted, except the
  site authoring workspace in `--authoring` mode (rw).
- `/home/pwuser/results` — results output directory. Host-mounted (rw) when
  `--result-dest=local`; container-internal when `--result-dest=s3`.
- `/home/pwuser/testscripts-cache` — S3 test script cache. Host-mounted (rw)
  when `--test-source=s3` only.

**Entry modes** of `run.py`:
- default (image `CMD`): prepare the merged test tree, run Playwright,
  write results.
- `--prepare-only`: prepare the merged test tree and determine the run
  mode exactly as the default mode does, then exit 0 (or 3 on error)
  without running tests. Used by `check_cep --shell`.

**Run mode**: if the root of the merged test tree contains a
Playwright config file, Playwright runs at the root with that config
and the config decides which tests run (project-root mode).
Otherwise `run.py` selects the test directory deterministically, as
documented in the container I/O contract (discovery mode).

**Time budget**: acquiring and merging the test tree counts toward
`PWTIMEOUT`. Source plugins receive the deadline explicitly and MUST
respect it; exceeding it is a protocol code 3.

**Output files** (written to `/home/pwuser/results`):
- `steps.json` — Playwright JSON reporter output.
- `test-meta.json` — runtime metadata (v2 schema): `started`
  (Unix epoch of host process start, from `CEP_STARTED` env var),
  `finished` (Unix epoch at write time), hostname, service,
  exit code, duration, probe location, status, `layers`
  (position, host path, type — never contents or injected values),
  and `versions` (`plugin` from `CEP_PLUGIN_VERSION`, `image` from
  the image's `CEP_IMAGE_VERSION`, `playwright` from the image's
  `PLAYWRIGHT_VERSION`; each `"unknown"` when not determinable).
- `playwright-report/` — HTML report directory.
- `screenshots/` — failure screenshots.

**Environment variables**: The container environment consists of
exactly three sources: (1) the image defaults plus the variables the
container runtime always sets, (2) the infrastructure variables
`check_cep` sets (plugin selectors, Nagios identifiers, timeout, the
layer list, plugin credentials when applicable, display variables in
headed mode), (3) operator-supplied variables (`--environ
NAME[=VALUE]`, all modes). Implicit forwarding of host variables by
the container runtime MUST be disabled. Values MUST NOT appear in the
container runtime's argv; the delivery mechanism is documented in the
container I/O contract. Names the plugin
sets itself are reserved and rejected for `--environ`. Key variables:
- `CEP_STARTED` — Unix epoch integer string of the host-side
  `check_cep` process start time. Used by `run.py` to populate
  `test-meta.json["started"]` and to identify the run directory
  when `%t` is used in `--result-dir`.
- `CEP_PLUGIN_VERSION` — release version of the host plugin
  (`CEP_VERSION`), passed on every run (reserved name). A plugin/image
  version mismatch is diagnostic only (`--debug`) and never changes
  the check result.

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

Raw codes of the Playwright process are mapped by a fixed table
(documented in the container I/O contract); in particular a raw 3 is
never passed through. The protocol MUST hold for every way `run.py`
can end: a top-level boundary MUST turn any uncaught exception, and
any exit that did not come from the protocol itself, into `3` with a
`CEPUNKNOWN` message — never Python's default exit code 1 (which
would read as WARNING). Protocol exits MUST pass this boundary
unchanged and without a second marker.

The host maps this protocol and the runtime's own codes to a
Nagios status per Principle III (Status classification).

Changes to this contract MUST be reviewed before implementation.

**Rationale**: A well-defined, documented contract keeps the host
and container sides decoupled. Conditional, read-only source mounts
reduce attack surface and guarantee that a run never changes its
own test source.

### V. Security by Default

All container executions MUST apply the principle of least
privilege within the constraints of E2E browser testing:

- Container MUST run as a non-root user (`pwuser`).
- Test sources MUST be mounted read-only and MUST NOT be modified by
  a run. The merged test tree is the only writable test location; it
  lives in the container's own filesystem and is discarded with the
  container. The rest of the container filesystem SHOULD be
  read-only where feasible.
- Plugin credentials (S3, Loki, registry) MUST only be used when the
  operator explicitly selects a plugin that requires them. The
  default configuration (`--test-source local`, `--result-dest
  local`, `--logging none`, no `--environ`) passes no credentials.
- Operator-supplied variables reach the container only when named
  explicitly, one `--environ` per variable; no other host variable
  is forwarded.
- Secret values (explicit `--environ` values, plugin credentials)
  MUST NOT appear in the container runtime's argv or in plugin log
  output, and MUST be masked in the Nagios output.
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
- **Playwright**: Installed inside the container via npm. The
  Playwright version and the base-image digest are defined once in
  `src/container/versions.env`; `package.json` pins
  `@playwright/test` exactly; `package-lock.json` is a committed
  derivation. Builds MUST fail when these sources disagree.
- **Monitoring Platform**: OMD (Open Monitoring Distribution) with
  Naemon core.
- **Host OS**: Linux (RHEL/Fedora family expected, but not
  mandated).
- **Test archive format**: gzip-compressed tar for S3 transport and
  for local archive layers; local layers may also be directories.
  No archive member, link or file may resolve outside the merged
  test tree.

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
- No change — feature or refactoring — may alter the plugin's
  external interface (command-line arguments and their semantics,
  exit codes and their meaning, output format) unless the change is
  listed in CHANGES.md. A change that contradicts a principle
  requires a constitution amendment first.

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

**Version**: 2.3.0 | **Ratified**: 2026-03-02 | **Last Amended**: 2026-10-27
