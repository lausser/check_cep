# RunContext: A Shared Execution Context for check_cep

## Problem Statement

`check_cep` accumulates a growing set of per-run state variables inside `main()`.
Each time a new piece of state is needed in a downstream function — as happened
with `started_str` in spec 009 — multiple function signatures must be updated,
even when the intermediate callers don't use the new value themselves.

Today the call chain looks like this:

```
main()
  │  hostname, servicedescription, started_str, testident, result_dir,
  │  start_time, timeout_deadline, omd_root, container_name, ...
  │
  ├─ build_env_vars(args, started_str)
  ├─ build_podman_command(container_bin, container_name, args, env_vars, result_dir)
  ├─ run_cleanup(plugin, parent_dir, current_run_dir, retention_seconds, timeout_deadline)
  └─ resolve_report_url(template, hostname, servicedescription, testident,
                        probe_location, s3_report_bucket, timestamp)
```

The variables `hostname`, `servicedescription`, `started_str`, `testident`, and
`timeout_deadline` are all computed once in `main()` and then threaded as
positional arguments through every call site that happens to need them.
Functions that don't need them can't easily ignore them either — they still
appear in the middle of long argument lists, creating noise and fragility.

The symptoms that make this a real maintenance burden:

- **Signature churn**: adding `started_str` in spec 009 required updating
  `build_env_vars`, and removing a redundant re-resolution from inside
  `build_podman_command` because the same template was being expanded twice.
- **Parameter overlap**: `args`, `hostname`, and `servicedescription` carry
  redundant information (`hostname == args.host_name`), but callers must pick
  the right source.
- **Hidden coupling**: `resolve_report_url` takes seven positional arguments,
  most of which come from the same namespace as the caller's locals.
- **Testing friction**: unit tests for individual functions must reconstruct
  the full parameter list even when only one value varies.


## Proposed Solution: `RunContext`

Introduce a single `RunContext` dataclass that is assembled once — immediately
after argument parsing and early validation — and passed as the sole context
argument to every function that needs shared state.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RunContext:
    # Identity
    hostname: str
    servicedescription: str
    testname: str          # "{hostname}/{servicedescription}" normalized
    testident: str         # URL-safe identifier for filenames
    container_name: str    # sanitized for Podman --name

    # Timing
    start_time: float      # time.time() at process entry
    started_str: str       # str(int(start_time)) — used in %t templates
    timeout_deadline: float  # start_time + args.timeout

    # Paths
    result_dir: str        # fully resolved (all template vars expanded)
    omd_root: str          # $OMD_ROOT or ""
    pid_file: str          # $OMD_ROOT/var/tmp/check_cep.{testident}.pid

    # Raw args (for everything not yet promoted to a typed field)
    args: object           # argparse.Namespace — intentionally untyped here
```

### Construction

`RunContext` is created exactly once, at the top of `main()`, after:
1. `args = parser.parse_args()`
2. `start_time = time.time()` and `started_str = str(int(start_time))`
3. Early exit checks (container env, headed validation, browser conflicts)
4. `result_dir` resolution via `resolve_path_template`

```python
ctx = RunContext(
    hostname=args.host_name,
    servicedescription=args.service_description,
    testname=derive_testname(args.host_name, args.service_description),
    testident=derive_testident(args.host_name, args.service_description),
    container_name=sanitize_container_name(testname),
    start_time=start_time,
    started_str=started_str,
    timeout_deadline=start_time + args.timeout,
    result_dir=resolve_path_template(args.result_dir, args.host_name,
                                     args.service_description, started=started_str),
    omd_root=omd_root,
    pid_file=os.path.join(omd_root or "/tmp", "var", "tmp",
                          f"check_cep.{testident}.pid"),
    args=args,
)
```

After this point, `main()` no longer refers to the individual variables
directly — it uses `ctx.hostname`, `ctx.result_dir`, etc.


## Before / After: Affected Functions

### `build_env_vars`

**Before**
```python
def build_env_vars(args, started_str: str = "") -> Dict[str, str]:
    ...
    env["CEP_STARTED"] = started_str
    env["HOSTNAME"] = args.host_name
    env["SERVICEDESC"] = args.service_description
    ...

# call site
env_vars = build_env_vars(args, started_str)
```

**After**
```python
def build_env_vars(ctx: RunContext) -> Dict[str, str]:
    ...
    env["CEP_STARTED"] = ctx.started_str
    env["HOSTNAME"] = ctx.hostname
    env["SERVICEDESC"] = ctx.servicedescription
    ...

# call site
env_vars = build_env_vars(ctx)
```

---

### `build_podman_command`

**Before**
```python
def build_podman_command(container_bin: str, container_name: str, args,
                         env_vars: Dict[str, str], result_dir: str) -> List[str]:
    ...

# call site
cmd = build_podman_command(containerenv.container_bin, container_name,
                           args, env_vars, result_dir)
```

**After**
```python
def build_podman_command(ctx: RunContext, container_bin: str,
                         env_vars: Dict[str, str]) -> List[str]:
    ...
    # container_name, result_dir, args.* all come from ctx

# call site
cmd = build_podman_command(ctx, containerenv.container_bin, env_vars)
```

The `container_bin` stays explicit because it is infrastructure state
(discovered from `ContainerEnv`), not part of the run identity.

---

### `run_cleanup`

**Before**
```python
def run_cleanup(
    plugin: ReportCleanupPlugin,
    parent_dir: str,
    current_run_dir: str,
    retention_seconds: int,
    timeout_deadline: float,
) -> CleanupResult:
    ...

# call site
run_cleanup(LocalCleanup(), parent_dir, result_dir,
            args.report_retention, start_time + args.timeout)
```

**After**
```python
def run_cleanup(plugin: ReportCleanupPlugin, ctx: RunContext) -> CleanupResult:
    parent_dir = os.path.dirname(ctx.result_dir)
    retention_seconds = ctx.args.report_retention  # or ctx.retention_seconds if promoted
    ...
    if time.time() > ctx.timeout_deadline - safety_margin:
        ...

# call site
run_cleanup(LocalCleanup(), ctx)
```

---

### `resolve_report_url`

**Before**
```python
def resolve_report_url(template: str, hostname: str, servicedescription: str,
                       testident: str, probe_location: str,
                       s3_report_bucket: str, timestamp: str) -> str:
    ...

# call site — 7 positional args
url = resolve_report_url(args.report_url, hostname, servicedescription,
                         testident, probe_location, s3_report_bucket, timestamp)
```

**After**
```python
def resolve_report_url(template: str, ctx: RunContext,
                       probe_location: str, s3_report_bucket: str,
                       timestamp: str) -> str:
    ...

# call site — 4 positional args
url = resolve_report_url(args.report_url, ctx, probe_location,
                         s3_report_bucket, timestamp)
```

The three remaining positional args (`template`, `probe_location`,
`s3_report_bucket`) are not in `RunContext` because they are either a
caller-controlled input (the template) or only known after the container
run completes (probe location, S3 bucket from steps.json).


## Design Decisions

### 1. `frozen=True`

`RunContext` is frozen. It represents what is known before the container
starts and must not change during the run. This makes it safe to pass into
threads (e.g., `CgroupPoller`) without locking.

### 2. Keep `args` in the context — for now

Extracting every `args.*` field into a typed slot would be complete but
expensive. The pragmatic approach: promote fields that appear in multiple
function signatures (`hostname`, `servicedescription`, `started_str`,
`result_dir`, `timeout_deadline`, `testident`), and leave the rest
accessible via `ctx.args.some_flag`. This can be done incrementally.

### 3. What does NOT belong in `RunContext`

- **Container output / result state**: `stdout`, `stderr`, `returncode`,
  `steps_data`, `perfdata`. These are produced by the container run and
  belong in a separate `RunResult` structure or remain as local variables
  in `main()`.
- **Infrastructure discovery**: `container_bin`, `has_cgroups2`, display
  server detection. These are `ContainerEnv` concerns.
- **Mutable poller state**: `CgroupPoller` is started and stopped around
  the container invocation and must stay mutable.

### 4. Separate `RunResult` (future)

The second half of `main()` — parsing `steps.json`, computing perfdata,
resolving the report URL, and calling `nagios_exit` — works with a
different set of values that are only available after the container exits.
A natural follow-on would be a `RunResult` dataclass:

```python
@dataclass
class RunResult:
    returncode: int
    wall_duration: int
    stdout_str: str
    stderr_str: str
    steps_data: Optional[dict]
    perfdata: List[Dict[str, Any]]
    container_output: str
    has_stderr_in_steps: bool
    cgroup_metrics: dict
```

`RunResult` is explicitly out of scope for the initial `RunContext` spec.
Introducing it later would allow the output-formatting logic to be
extracted from `main()` into a standalone function, further shrinking the
function.


## Migration Strategy

The refactor is mechanical and carries zero behaviour risk, but `main()` is
large and touches many functions. Recommended approach:

**Phase 1 — Define and construct, no callers changed**
Add the `RunContext` dataclass. Populate it in `main()` alongside the
existing local variables (both exist simultaneously). No function signatures
change yet. Run full test suite: nothing should break.

**Phase 2 — Migrate one function at a time**
Convert each function to accept `ctx: RunContext`, update its call site in
`main()`, remove the now-redundant local variable if it was only needed for
that call. Suggested order (most parameters removed first):
1. `resolve_report_url` (7 → 4 args)
2. `build_podman_command` (5 → 3 args)
3. `run_cleanup` (5 → 2 args)
4. `build_env_vars` (2 → 1 arg)
5. `resolve_path_template` (4 → 2 args: template + ctx)

Each function is an independent, reviewable commit.

**Phase 3 — Clean up `main()`**
Remove the individual local variable assignments that are now only accessed
via `ctx`. At this point `main()` should read as: parse → validate → build
context → run container → format output.


## Testing Impact

- **Unit tests**: functions that currently require 5–7 positional args can
  be called with a single `make_ctx(**overrides)` helper that returns a
  `RunContext` with sensible defaults. This dramatically reduces test setup
  boilerplate.
- **Existing tests**: no behaviour change means existing integration tests
  need no modification.
- **New tests**: the `RunContext` constructor itself is worth a small unit
  test suite verifying that template expansion and deadline computation are
  correct at construction time, rather than scattered through callers.


## Summary

| Function | Args today | Args after |
|---|---|---|
| `build_env_vars` | 2 | 1 (`ctx`) |
| `build_podman_command` | 5 | 3 (`ctx`, `container_bin`, `env_vars`) |
| `run_cleanup` | 5 | 2 (`plugin`, `ctx`) |
| `resolve_report_url` | 7 | 4 (`template`, `ctx`, `probe_location`, `s3_bucket`) |
| `resolve_path_template` | 4 | 2 (`template`, `ctx`) |

Total positional arguments removed across these five functions: **14 → 13**
in absolute count, but the duplication across call sites is what shrinks —
`hostname` appears today in four separate argument lists; after the refactor
it appears once, in the `RunContext` constructor.
