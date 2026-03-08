# check_cep Tutorial

This tutorial walks you through building the container image, writing your first
Playwright test, and running it with `check_cep`.

## Prerequisites

- **Podman** installed and working (rootless mode is fine)
- **Python 3** on the host (for `check_cep` itself)
- Internet access (to pull the base image and for tests to reach target websites)

### Rootless Podman Setup for OMD Site Users

---

#### Quick Setup (copy & paste)

Run all of this as **root**, then open a fresh SSH session as the site user:

```bash
# 1. Subordinate UID/GID ranges — lets Podman create user namespaces
usermod --add-subuids 100000-165535 --add-subgids 100000-165535 cep

# 2. Linger — keeps the systemd user session alive without a login
loginctl enable-linger cep

# 3. Delegate the io cgroup controller — required for I/O metrics
mkdir -p /etc/systemd/system/user@.service.d
cat > /etc/systemd/system/user@.service.d/delegate.conf << 'EOF'
[Service]
Delegate=cpu cpuset io memory pids
EOF
systemctl daemon-reload
systemctl restart user@$(id -u cep).service
```

Quick sanity check:

```bash
grep -q io /sys/fs/cgroup/user.slice/cgroup.subtree_control && echo "io: OK" || echo "io: MISSING"
```

Then log in as `cep` in a **new SSH session** (not `su`) and run a test check.

---

#### Technical Background (for the seasoned systemd admin)

Three separate Linux subsystems must cooperate for rootless Podman to work
correctly as an OMD site user. Each prerequisite fixes a failure in a different
layer of the stack.

**1. User namespaces and subordinate ID maps**

Rootless Podman isolates containers using Linux user namespaces
(`clone(CLONE_NEWUSER)`). Inside the container, processes appear to run as a
range of UIDs (root at UID 0, `pwuser` at UID 1000, etc.). On the host these
map to a contiguous block of *subordinate* UIDs owned by the site user.

The kernel learns about this mapping from `/etc/subuid` and `/etc/subgid`.
`usermod --add-subuids` appends the entry. `newuidmap(1)` and `newgidmap(1)`
(setuid helpers, part of `shadow-utils`) then write the actual
`/proc/self/uid_map` inside the new namespace. Without a subuid entry the
kernel refuses the `uid_map` write and Podman aborts before the container
even starts.

The range `100000–165535` (65536 entries) is the conventional default. It is
wide enough to map a full 16-bit UID space inside the container and avoids
collisions with real system UIDs (< 1000) and typical user UIDs (1000–60000).

**2. Systemd linger and the user session unit**

Podman's cgroup v2 support relies on the *systemd user bus*
(`/run/user/UID/bus`), which is only available when `user@UID.service` is
running. Normally systemd starts this unit when the user opens a session and
stops it when the last session ends.

`loginctl enable-linger cep` creates a marker in `/var/lib/systemd/linger/`
that causes `systemd-logind` to start `user@UID.service` at boot and keep it
alive indefinitely — regardless of whether the user is logged in. Without
linger, a Naemon check running as `cep` via `sudo -u cep` or `su -s /bin/sh`
has no systemd session, Podman falls back to the raw `cgroupfs` driver, and
cgroup v2 resource tracking is unreliable.

**3. Cgroup controller delegation and io.stat**

This is the subtlest of the three. Cgroup v2 uses a *controller delegation*
model: a parent cgroup explicitly lists which resource controllers it passes
down to children by writing to `cgroup.subtree_control`. A controller that is
not listed there is simply absent from all descendant cgroups — the
corresponding pseudo-files (`io.stat`, `cpu.stat`, etc.) do not exist.

The delegation chain for the site user looks like this:

```
/sys/fs/cgroup/                         ← root cgroup (kernel-managed)
  └── user.slice/                        ← all user sessions
        └── user-999.slice/              ← sessions for uid 999 (cep)
              └── user@999.service/      ← the user manager itself
                    └── app.slice/       ← transient container cgroups land here
                          └── libpod-<ID>.scope/
```

Systemd reads `Delegate=` from the unit file and writes those controller names
into `cgroup.subtree_control` when it starts the unit. The stock
`user@.service` in most distributions ships with:

```
Delegate=pids memory cpu
```

This is intentionally conservative — `io` throttling interacts with the block
layer and can degrade I/O performance if misused, so upstream chose not to
delegate it by default.

The consequence: `io.stat` does not exist anywhere in the
`user-999.slice/` subtree, so `check_cep`'s cgroup polling thread finds no
file to read and sets `podman_metric_collection_failed=1`.

The drop-in `/etc/systemd/system/user@.service.d/delegate.conf` overrides the
`Delegate=` line for every user session on the host. After
`systemctl daemon-reload` + `systemctl restart user@999.service`, systemd
writes `cpuset cpu io memory pids` into
`/sys/fs/cgroup/user.slice/cgroup.subtree_control` and propagates it down the
slice tree, making `io.stat` available inside every container cgroup created
under that user session.

Note that `Delegate=` is *additive across drop-ins* only within a single
`[Service]` section — it does **not** merge with the base file. The drop-in
must therefore list the complete desired set, not just `io`.

`cpuset` is included so that Podman can honour CPU-pinning requests
(`--cpuset-cpus`); it is a no-op if unused.

## 1. Build the Container Image

The image is built from the `src/` directory. You must pass the Playwright version
as a build argument. The version determines which Microsoft Playwright base image
is used.

```bash
cd src/
podman build \
  --build-arg PLAYWRIGHT_VERSION=v1.58.2 \
  -t localhost/check_cep:latest .
```

This takes a few minutes on the first run (downloading browsers). Subsequent
builds are fast thanks to layer caching.

### Custom npm Dependencies

If your tests need additional npm packages (e.g. `@axe-core/playwright`), replace
the zero-byte `src/package.json` and `src/package-lock.json` with real ones before
building. The Dockerfile detects a non-empty `package-lock.json` and runs `npm ci`
automatically.

## 2. Prepare Test Files

Create a directory for your test. The directory needs at minimum:

- `playwright.config.ts` — Playwright configuration
- `tests/` subdirectory — containing one or more `*.test.ts` files

### Example: Testing consol.de

```bash
mkdir -p /tmp/my-first-test/tests
```

Create the Playwright config:

```bash
cat > /tmp/my-first-test/playwright.config.ts << 'EOF'
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
EOF
```

Create a test file:

```bash
cat > /tmp/my-first-test/tests/consol.test.ts << 'EOF'
import { test, expect } from '@playwright/test';

test('consol.de has Consulting & Solutions', async ({ page }) => {
  await page.goto('https://www.consol.de');
  await expect(page.locator('body')).toContainText('Consulting & Solutions');
});
EOF
```

### Directory Layout

Your test directory should look like this:

```
/tmp/my-first-test/
  playwright.config.ts
  tests/
    consol.test.ts
```

You can have multiple test files, helper modules, and fixture files. Playwright
discovers all `*.test.ts` / `*.test.js` files under the configured `testDir`.

## 3. Run the Test

```bash
python3 src/check_cep \
  --host-name testhost \
  --service-description Consol_Homepage \
  --image localhost/check_cep:latest \
  --probe-location local \
  --test-source local \
  --result-dest local \
  --test-dir /tmp/my-first-test \
  --result-dir /tmp/my-first-results \
  --timeout 60
```

### What Happens

1. `check_cep` creates the result directory (`/tmp/my-first-results`)
2. It starts a Podman container with:
   - your test directory mounted read-only at `/home/pwuser/tests`
   - the result directory mounted read-write at `/home/pwuser/results`
3. Inside the container, `run.py` runs `npx playwright test`
4. Playwright writes `steps.json`, an HTML report, and (on failure) screenshots
5. The container fixes result file ownership (see below)
6. `check_cep` reads the results and prints a Nagios status line

### Expected Output (passing test)

```
OK - test Consol_Homepage succeeded | 'TestDuration'=1250ms 'duration'=5s 'podman_cpu_usage'=6.79s ...
```

### Expected Output (failing test)

```
CRITICAL - test Consol_Homepage failed | 'duration'=4s ...
```

The exit code follows Nagios conventions:

| Exit Code | Meaning |
|-----------|---------|
| 0         | OK — all tests passed |
| 1         | WARNING — tests passed but stderr was found |
| 2         | CRITICAL — test failure, timeout, or OOM |
| 3         | UNKNOWN — configuration error, missing files |

## 4. Inspect the Results

After a run, the result directory contains:

```
/tmp/my-first-results/
  steps.json              # Structured test results (durations, errors, stdout/stderr)
  test-meta.json          # Runtime metadata (hostname, status, duration, timestamp)
  playwright-report/
    index.html            # Interactive HTML report — open in a browser
  test-results/           # Screenshots and traces (on failure)
```

All files are owned by the user who called `check_cep` — not by a container
internal uid. See [File Ownership](#file-ownership-in-local-mode) below for
details.

### View the HTML Report

```bash
xdg-open /tmp/my-first-results/playwright-report/index.html
# or on macOS:
open /tmp/my-first-results/playwright-report/index.html
```

### Inspect test-meta.json

```bash
cat /tmp/my-first-results/test-meta.json
```

```json
{
    "timestamp": "1772635413",
    "hostname": "testhost",
    "servicedescription": "Consol_Homepage",
    "exitcode": 0,
    "duration": "6.513",
    "probe_location": "local",
    "status": "OK"
}
```

### Inspect steps.json

`steps.json` contains the full Playwright JSON reporter output — test durations,
individual step timings, stdout, stderr, and error messages. This is the primary
data source for the performance data (`'TestDuration'=...`) in the Nagios output.

## 5. File Ownership in Local Mode

When `--result-dest local` is used, Podman mounts the result directory into the
container. Playwright runs as `pwuser` (a non-root user inside the image), so all
written files initially appear on the **host** owned by an unpredictable sub-uid
— typically a large number like `525287` — that is not your user:

```
-rw-r--r--. 1 525287 525287 2615 Mar  4 16:44 steps.json   ← hard to delete!
```

`check_cep` solves this automatically. Before the container exits,
`dest_local.py` runs:

```bash
sudo chown -R root:root ~/results
sudo chmod -R u+rwX,go+rX ~/results
```

**Why `chown root` works**: in rootless Podman, `root` inside the container maps
exactly to the uid of the user who invoked `podman run` on the host. So `chown
root` from inside the container transfers ownership to your user outside it.

After a successful run, result files are owned normally:

```
-rw-r--r--. 1 yourusername yourusername 2615 Mar  4 17:02 steps.json
```

This requires `pwuser` to have passwordless `sudo`, which the Dockerfile
configures via `/etc/sudoers.d/pwuser`.

## 7. Debug a Failing Test

### Add `--debug` for Verbose Logging

```bash
python3 src/check_cep \
  --host-name testhost \
  --service-description Consol_Homepage \
  --image localhost/check_cep:latest \
  --probe-location local \
  --test-source local \
  --result-dest local \
  --test-dir /tmp/my-first-test \
  --result-dir /tmp/my-first-results \
  --timeout 60 \
  --debug
```

This shows the full `podman run` command and container debug output.

### Use `--shell` to Enter the Container

```bash
python3 src/check_cep \
  --host-name testhost \
  --service-description Consol_Homepage \
  --image localhost/check_cep:latest \
  --probe-location local \
  --test-source local \
  --result-dest local \
  --test-dir /tmp/my-first-test \
  --result-dir /tmp/my-first-results \
  --timeout 60 \
  --shell
```

This drops you into a bash shell inside the container. From there you can run
Playwright manually:

```bash
cd ~/tests
npx playwright test --reporter=line
```

## 8. Headed Mode — Debug with a Real Browser on Your Desktop

When a test fails and the HTML report doesn't tell the whole story, you can watch
Playwright drive a real browser window on your desktop. The `--headed` flag
forwards the container's X11 connection to your host display.

### Prerequisites

- A **Linux desktop session** (KDE Plasma, GNOME, Xfce, etc.) — Wayland desktops
  work fine because XWayland provides an X11 server automatically
- `xhost` installed (usually part of `xorg-x11-server-utils` or `xhost`)
- `DISPLAY` environment variable set (happens automatically in desktop terminals)

> **Why X11 and not native Wayland?** Chrome/Chromium on Linux still uses X11
> under the hood (even on Wayland, it connects via XWayland). X11 socket
> forwarding into containers is simple and proven. Native Wayland forwarding
> requires complex `XDG_RUNTIME_DIR` sharing and a wayland-proxy — not worth
> the complexity for a debug tool.

### Quick Start

```bash
python3 src/check_cep \
  --headed \
  --host-name testhost \
  --service-description Consol_Homepage \
  --image localhost/check_cep:latest \
  --probe-location local \
  --test-source local \
  --result-dest local \
  --test-dir /tmp/my-first-test \
  --result-dir /tmp/my-first-results \
  --timeout 60
```

A Chromium window opens on your desktop, navigates to the target site, and you
can watch every click and assertion happen in real time. When the test finishes,
the window closes and `check_cep` produces its normal Nagios output.

### Combine with `--shell` for Interactive Debugging

The most powerful debug workflow: `--headed --shell` drops you into the container
with X11 forwarding already configured. You can then run Playwright manually,
re-run individual tests, or experiment with selectors — all with a visible
browser.

```bash
python3 src/check_cep \
  --headed --shell \
  --host-name testhost \
  --service-description Consol_Homepage \
  --image localhost/check_cep:latest \
  --probe-location local \
  --test-source local \
  --result-dest local \
  --test-dir /tmp/my-first-test \
  --result-dir /tmp/my-first-results \
  --timeout 60
```

Inside the container:

```bash
cd ~/tests
npx playwright test --headed --reporter=line     # run all tests with visible browser
npx playwright test --headed -g "has title"       # run a single test by name
npx playwright test --headed --debug              # Playwright Inspector (step-through)
```

### What `--headed` Does Under the Hood

`check_cep` adds several Podman flags that are **only** active in headed mode:

| Podman flag | Purpose |
|-------------|---------|
| `--userns=keep-id:uid=1001,gid=1001` | Maps your host UID to `pwuser` (UID 1001) inside the container, so the container process can read the X11 socket |
| `--security-opt label=disable` | Disables SELinux labeling — the X11 socket cannot use `:z` relabeling since it's shared with the host |
| `--ipc=host` | Shares the host's IPC namespace — Chrome requires the MIT-SHM X extension and crashes without it |
| `--volume /tmp/.X11-unix:/tmp/.X11-unix:ro` | Mounts the X11 unix socket (no `:z` — relabeling a shared host socket would break other X11 clients) |
| `--env DISPLAY=$DISPLAY` | Tells the browser which X display to connect to |
| `--volume ~/.Xauthority:/tmp/.Xauthority:ro` | X11 authentication cookie (only if the file exists) |

Before starting the container, `check_cep` also runs `xhost +local:` to allow
local connections to the X display.

### Error Messages

If the environment doesn't support headed mode, `check_cep` exits UNKNOWN with
a clear message:

| Message | Fix |
|---------|-----|
| `--headed requires DISPLAY to be set` | Run from a desktop terminal, not an SSH session |
| `--headed: X11 socket /tmp/.X11-unix/X0 not found` | Your X server isn't running; log in to a graphical desktop |
| `--headed requires xhost to be installed` | Install `xorg-x11-server-utils` (Fedora) or `x11-xserver-utils` (Debian) |

### When to Use Headed Mode (and When Not To)

**Good uses:**
- Debugging a flaky test — watch what happens visually
- Writing a new test — iterate with `--headed --shell` and a visible browser
- Investigating timing issues — see if the page actually loaded before the assertion ran
- Using Playwright Inspector (`--debug`) for step-through debugging

**Not appropriate for:**
- Production monitoring (headless is the default for a reason)
- CI pipelines (no display)
- Automated test runs (adds overhead and requires a desktop session)

## 9. OMD Integration

In a production OMD environment, the default paths are:

| Path | Purpose |
|------|---------|
| `$OMD_ROOT/etc/check_cep/tests/<HOSTNAME>/<SERVICE>/` | Test scripts |
| `$OMD_ROOT/var/tmp/check_cep/<HOSTNAME>/<SERVICE>/` | Results |

Both support `%h` (hostname) and `%s` (service description) template variables.

### Naemon Service Definition

```
define service {
    host_name               webserver01
    service_description     E2E_Login_Check
    check_command           check_cep!localhost/check_cep:latest!datacenter-eu
    ...
}

define command {
    command_name    check_cep
    command_line    $OMD_ROOT/local/lib/nagios/plugins/check_cep \
                    --host-name '$HOSTNAME$' \
                    --service-description '$SERVICEDESC$' \
                    --image '$ARG1$' \
                    --probe-location '$ARG2$' \
                    --test-source local \
                    --result-dest local
}
```

This runs the tests at `$OMD_ROOT/etc/check_cep/tests/webserver01/E2E_Login_Check/`
and writes results to `$OMD_ROOT/var/tmp/check_cep/webserver01/E2E_Login_Check/`.

## 10. CLI Reference

### Required Arguments

| Argument | Description |
|----------|-------------|
| `--host-name` | Naemon `$HOSTNAME$` macro |
| `--service-description` | Naemon `$SERVICEDESC$` macro |
| `--image` | Container image name with tag |
| `--probe-location` | Geographic location identifier |

### Common Options

| Argument | Default | Description |
|----------|---------|-------------|
| `--test-source` | `local` | `local` or `s3` |
| `--result-dest` | `local` | `local` or `s3` |
| `--logging` | `none` | `none` or `loki` |
| `--test-dir` | `$OMD_ROOT/etc/check_cep/tests/%h/%s` | Host-side test directory |
| `--result-dir` | `$OMD_ROOT/var/tmp/check_cep/%h/%s` | Host-side result directory |
| `--timeout` | `60` | Container timeout in seconds |
| `--memory-limit` | `2g` | Container memory limit |
| `--debug` | off | Verbose logging |
| `--shell` | off | Interactive bash shell |
| `--headed` | off | X11-forwarded headed browser (debug only) |

### Performance Data

Each successful run produces these metrics in the Nagios perfdata:

| Metric | Unit | Description |
|--------|------|-------------|
| `TestDuration` | ms | Playwright test execution time |
| `duration` | s | Total wall-clock time |
| `podman_cpu_usage` | s | Total CPU seconds consumed |
| `podman_peak_cpu` | % | Peak CPU utilization |
| `podman_memory_current` | B | Memory at container exit |
| `podman_memory_peak` | B | Peak memory usage |
| `podman_io_bytes_read` | B | Disk I/O read |
| `podman_io_bytes_write` | B | Disk I/O written |
| `podman_oom_killed` | 0/1 | Whether the container was OOM-killed |

---

## 11. Testing the check_cep Plugin Itself

> **Scope clarification** — This section is about testing the software in **this
> repository** (the `check_cep` plugin and its supporting Python code). It is
> completely separate from the primary purpose of check_cep, which is to run
> Playwright end-to-end browser tests against your own websites and services.
> If you are looking for how to write E2E tests for a website, see sections 2–4
> above.

### What Is Tested

The integration test suite in `tests/` verifies that check_cep itself behaves
correctly under a range of conditions:

| Test file | What it covers |
|-----------|----------------|
| `test_check_cep.py` | Core scenarios: passing test, failing test, timeout, syntax error, perfdata, result files |
| `test_modes.py` | Five fixture files × local mode and S3 mode (parametrized) |
| `test_collision.py` | Concurrent duplicate run is blocked within seconds |
| `test_loki.py` | Loki log forwarding: entry received; dead endpoint is non-fatal |

The five Playwright fixtures used by `test_modes.py` live in `tests/fixtures/`
and target `https://practice.expandtesting.com/` — a public site designed for
end-to-end test practice. They exercise a passing scenario (`tc_pass`), a
registration flow (`tc_register_pass`), a deliberate failure (`tc_fail`), a
hang/timeout (`tc_timeout`), and a TypeScript syntax error (`tc_syntax`).

### Prerequisites

- **Podman** installed and working (rootless)
- **Python 3.9+** with `pytest` (`pip install pytest`)
- **For S3 and Loki tests only**: `podman-compose` and `boto3`
  (`pip install podman-compose boto3`)
- **Internet access** for `tc_pass` and `tc_register_pass` fixture tests

### Makefile Targets

A `Makefile` at the repository root provides convenient entry points:

```bash
make help          # Show all available targets
make image         # Build production image (localhost/check_cep:latest + version tag)
make test-image    # Build check_cep:test image (for development iteration)
make test-local    # Build test image + run tests without external services
make test-all      # Build test image + run full suite including S3 and Loki tests
make test-clean    # Stop and remove the MinIO + Loki compose stack
```

### Quick Start: Local-Only Tests

```bash
# Run local-mode tests — no MinIO, no Loki required
# (automatically builds check_cep:test if src/container/ changed)
make test-local
```

This runs `SKIP_INTEGRATION=1 pytest tests/integration/ -v`, which covers all
of `test_check_cep.py`, all `test_local[*]` cases in `test_modes.py`, and
`test_collision.py`. S3 and Loki tests are automatically skipped.

Expected output (abridged):

```
tests/integration/test_check_cep.py::test_passing PASSED
tests/integration/test_check_cep.py::test_failing PASSED
...
tests/integration/test_modes.py::test_local[tc_pass] PASSED
tests/integration/test_modes.py::test_local[tc_register_pass] PASSED
tests/integration/test_modes.py::test_local[tc_fail] PASSED
tests/integration/test_modes.py::test_local[tc_timeout] PASSED
tests/integration/test_modes.py::test_local[tc_syntax] PASSED
tests/integration/test_collision.py::test_collision PASSED
```

### Full Suite: Including S3 and Loki

```bash
make test-all      # builds test image, starts compose stack, runs everything, tears down
```

`make test-all` runs `pytest tests/integration/ -v`. The session-scoped
`compose_stack` fixture starts MinIO and Loki automatically, waits for them to
become ready, creates the required buckets, runs all tests, and then tears down
the stack. No manual `podman-compose` invocation needed.

To leave the stack running between runs for faster iteration:

```bash
podman-compose -f tests/compose/docker-compose.yml up -d   # start once
pytest tests/integration/ -v                               # run tests repeatedly
make test-clean                                             # stop when done
```

### Overriding the Container Image

`make test-image` tags the image as `check_cep:test` — deliberately separate from
the production `localhost/check_cep:latest` so you can iterate on `run.py` or the
Dockerfile without affecting the production image.

```bash
# Use a specific image (e.g. a production build) instead of the test image
CEP_IMAGE=localhost/check_cep:latest make test-local
CEP_IMAGE=localhost/check_cep:latest make test-all
```

### Running a Single Test File or Case

```bash
pytest tests/integration/test_modes.py -v
pytest "tests/integration/test_modes.py::test_local[tc_fail]" -v
SKIP_INTEGRATION=1 pytest tests/integration/test_modes.py -k local -v
```

### Test Structure

```
tests/
├── conftest.py                    # Session fixtures: cep_image, compose_stack,
│                                  #   write_playwright_config
├── fixtures/                      # Playwright .test.ts files used as test inputs
│   ├── tc_pass/tc_pass.test.ts
│   ├── tc_register_pass/tc_register_pass.test.ts
│   ├── tc_fail/tc_fail.test.ts
│   ├── tc_timeout/tc_timeout.test.ts
│   └── tc_syntax/tc_syntax.test.ts
├── compose/
│   └── docker-compose.yml         # MinIO + Loki service definitions
└── integration/
    ├── conftest.py                 # Helpers: run_check_cep(), run_check_cep_s3(),
    │                               #   local_test_dir(), query_loki(), omd_env, test_env
    ├── test_check_cep.py           # Core scenario tests
    ├── test_modes.py               # Parametrized: 5 fixtures × {local, s3}
    ├── test_collision.py           # Concurrent duplicate detection
    └── test_loki.py                # Loki log forwarding
```
