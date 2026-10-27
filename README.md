# check_cep Tutorial

![check_cep: passing login test with vision highlights, Playwright report, failing test showing invalid credentials, and error details](docs/teaser.gif)

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

> **Want to understand *why* each step is needed?** See [Appendix A — Rootless
> Podman Internals](#appendix-a--rootless-podman-internals) at the end of this
> document for a deep dive into user namespaces, systemd linger, and cgroup
> controller delegation.
>
> **`--headed` / `--vnc` / `--authoring` fail with `OCI permission denied`
> on `…/overlay/…/merged`?** The site home is too tight for `--userns=keep-id`.
> See [Permission denied making overlay merged private](#permission-denied-making-overlay-merged-private).

---

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

A check's tests form an ordinary Playwright project. check_cep runs it in one
of two *run modes* (details in
[WRITING-TESTS.md](WRITING-TESTS.md#folder-structure)):

- **Project-root mode** (recommended): a `playwright.config.ts` at the top of
  the tree. Playwright runs from there with that config and decides which
  tests run (`testDir`, `testMatch`, `*.spec.ts` and `*.test.ts`, setup
  projects) — exactly as on a developer machine.
- **Discovery mode**: no config at the top. check_cep picks the first
  directory, in byte-wise path order, that contains `*.test.ts`/`*.test.js`
  and runs Playwright there (the layout used before spec 023).

The example below uses project-root mode. It needs:

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

Inside the container the same files are
`/home/pwuser/tests/playwright.config.ts` and
`/home/pwuser/tests/tests/consol.test.ts`. `/home/pwuser/tests` is the
*check root* (everything check_cep merged for this check), not a folder of
tests, so the doubled `tests/tests` is expected.

Because `playwright.config.ts` sits at the top, this is project-root mode:
Playwright finds all `*.test.ts` / `*.spec.ts` files under the configured
`testDir`. You can have multiple test files, helper modules, and fixture files.

### Layers

`--test-artifact` is repeatable. Each value is a *layer*: a directory or a
`.tgz`/`.tar.gz` archive. check_cep merges the layers, in command-line order,
into one tree, the check root `/home/pwuser/tests` inside the container:

- For the same relative path, the later layer wins; directories merge
  recursively; dotfiles are included. With `--debug`, every override is
  logged (`override: playwright.config.ts layer 2 wins over layer 1`).
- `%h` (host name) and `%s` (service description) are expanded in every
  value, so one Naemon command can serve every service.
- The sources are mounted read-only and never modified. The merged tree is a
  writable copy per run (tests may write into it, e.g.
  `playwright/.auth/user.json`) and is discarded after the run.
- The run mode is decided on the merged tree, never on a single layer.
- Layers are local only. `--test-source s3` takes exactly one
  `--test-artifact`; `--authoring` ignores them (with a warning for more
  than one).
- Without `--test-artifact`, the implicit default
  `$OMD_ROOT/etc/check_cep/tests/%h/%s` (or the deprecated `--test-dir`) is
  the only layer.
- Layers have no roles; only their order matters. Typical arrangements:
  - *enterprise → project → service*: a shared layer with
    `playwright.config.ts`, `tsconfig.json` and helpers; a project layer;
    the service's tests.
  - *final override layer*: a last, probe-specific layer that replaces one
    file, e.g. a `playwright.config.ts` with this probe location's proxy.
  - *single layer*: one directory or archive, as before.
- `package.json` and `node_modules` in a layer are ignored; only the packages
  in the image are available.

A misconfigured layer gives UNKNOWN before or instead of a test run: a
missing path or an unsupported type (`--test-artifact #2 (<path>): does not
exist`), a corrupt or unsafe archive, a symbolic link pointing outside the
tree, a file in one layer where another has a directory (`type conflict at
functions`), or a merged tree without tests.

Example Naemon command with a shared layer and one per service:

```cfg
define command {
  command_name  check_cep_layered
  command_line  $USER1$/check_cep --host-name '$HOSTNAME$' --service-description '$SERVICEDESC$' \
                --image check_cep:latest --probe-location $_HOSTPROBE$ \
                --test-artifact $USER5$/check_cep/layers/enterprise \
                --test-artifact $USER5$/check_cep/tests/%h/%s \
                --environ APP_PASSWORD
}
```

### Don't want to write the test yourself?

The `ai` image includes an **AI-assisted authoring** workflow: a
non-technical user describes the check in a plain-language intent file
(`*.ai`), and an admin runs a supervised session that explores the site and
writes a deterministic test — no hand-written code. The deployed check runs
with no AI at run time.

Build the image once (`make image-ai`, see *Makefile Targets* above), then:

```bash
check_cep --host-name onvista --service-description Portfolio \
          --image check_cep:ai --probe-location dev --authoring
```

See the **AI-Assisted Test Authoring** chapter in
[WRITING-TESTS.md](WRITING-TESTS.md#ai-assisted-test-authoring) for the full
walkthrough (the intent template, the supervised session, review, and
packaging).

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
   - your test directory mounted read-only as a layer, which `run.py` copies
     into the writable check root `/home/pwuser/tests` before each run
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
    "started": "1772635407",
    "finished": "1772635413",
    "hostname": "testhost",
    "servicedescription": "Consol_Homepage",
    "exitcode": 0,
    "duration": "6.513",
    "probe_location": "local",
    "status": "OK",
    "layers": [
        {"position": 1, "path": "/tmp/my-first-test", "type": "directory"}
    ]
}
```

`layers` lists the test layers in merge order with their host paths (for S3:
`s3:/<bucket>/<key>`). Both `started` and `finished` are Unix epoch integer strings. `started` reflects
the host-side `check_cep` process start time; `finished` is when the container
wrote the file. The directory name matches `started` when `%t` is used.

### Inspect steps.json

`steps.json` contains the full Playwright JSON reporter output — test durations,
individual step timings, stdout, stderr, and error messages. This is the primary
data source for the performance data (`'TestDuration'=...`) in the Nagios output.

### Per-Run Directories with `%t`

Add `%t` to `--result-dir` to create an isolated, timestamped directory for each
run instead of overwriting results from previous runs:

```bash
check_cep \
  --host-name myhost \
  --service-description Formular \
  --result-dir /omd/sites/cep/var/tmp/check_cep/%h/%s/%t \
  --report-url http://cep-host/reports/%h/%s/%t/playwright-report/index.html \
  ...
```

Each run creates a directory named after the Unix epoch of its start time
(e.g. `/omd/.../Formular/1710763200/`), keeping all runs independent.

To automatically delete old run directories, add `--report-retention`:

```bash
# Keep only the last 24 hours of reports; delete everything older
check_cep \
  --result-dir .../check_cep/%h/%s/%t \
  --report-retention 24h \
  ...
```

Cleanup runs after each check, deleting oldest-first, and always stops with at
least 10 seconds remaining before the plugin timeout.

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

## 6. Secrets and `--environ`

Tests read secrets from `process.env`. `--environ` passes a variable into the
test container in **every** mode — scheduled checks, `--shell`, `--headed`,
`--vnc` and `--authoring` (repeatable):

| Form | Effect |
|---|---|
| `--environ APP_PASSWORD` (bare) | forwards the value check_cep itself has in its environment; unset → UNKNOWN before the container starts |
| `--environ APP_PASSWORD=s3cret` (explicit) | sets the value byte-for-byte (spaces, quotes, `=`, newlines) |
| `--environ APP_PASSWORD=` | sets the empty string (not masked) |

The last occurrence of a name wins. Only named variables reach the container;
nothing from the host environment is forwarded implicitly.

**Recommendation**: put the secret into the environment of check_cep (e.g. a
Naemon environment macro) and use the bare form — then the value never
appears on any command line.

### Secret exposure model

| Where a value can be seen | Bare `--environ NAME` | Explicit `--environ NAME=VALUE` |
|---|---|---|
| check_cep's own command line (`ps`, visible to **all** local users) | not visible | **visible** — unavoidable, documented |
| Container runtime command line (`ps`, all users) | not visible | not visible (FR-004) |
| Plugin debug log (`--debug`) | not visible | not visible (FR-004) |
| Process/container environment (`/proc/<pid>/environ`, `podman inspect`; same user or root only) | visible | visible |
| Nagios status line and long output (GUI, notifications, history) | masked (FR-009) | masked (FR-009) |
| Playwright reports, traces, screenshots, videos | test author's responsibility | test author's responsibility |

The plugin's own credentials (`--aws-access-key-id`,
`--aws-secret-access-key`, `--loki-password`, `--registry-password`) follow
the explicit-form column: they are passed to podman by name only (the
registry login reads the password from stdin), never logged, and masked in
the output.

### Output masking

Every non-empty `--environ` value and plugin credential is replaced by `***`
in the Nagios status line and long output (including container output
forwarded with `--debug`). Perfdata and the files in the results directory
are not masked. Masking replaces *every* occurrence, so a short or common
value (`1`, `admin`, `true`) also masks unrelated text — use distinctive
values. Values typed into pages or printed by tests can still appear in
traces, screenshots, videos and HTML reports, which masking does not cover.

### Reserved names

check_cep sets these variables itself; `--environ` rejects them with UNKNOWN
(`--environ NAME: reserved, check_cep sets this variable itself`):

- exact names: `TEST_SOURCE`, `RESULT_DEST`, `LOGGING`, `PWTIMEOUT`,
  `PROBE_LOCATION`, `TESTIDENT`, `TERM`, `FORCE_COLOR`, `CEP_STARTED`,
  `DEBUG`, `HEADED`, `BROWSER`, `REPORT_PATH`, `CEP_SLOW_MO`,
  `CEP_VISION_HIGHLIGHT_MS`
- prefixes: `NAGIOS_`, `TEST_ARTIFACT`, `S3_`, `AWS_`, `LOKI_`

The display variables (`DISPLAY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`,
`XAUTHORITY`) are not reserved, but in `--headed`/`--vnc` mode the plugin's
own values win. `OPENCODE_CONFIG` is allowed; with `--authoring
--opencode-config` the overlay path wins.

### Container environment

The container environment has exactly three sources: the image defaults
(plus `container`, `HOSTNAME` and `HOME`, which podman always sets), the
variables check_cep sets itself, and the `--environ` names. Every
`podman run` gets `--http-proxy=false --env-host=false`, so podman no longer
forwards host proxy variables (`http_proxy`, `https_proxy`, `ftp_proxy`,
`no_proxy`, either case) or a site's `env_host = true` environment.

A check behind a proxy names it explicitly:

1. **Traffic to the application under test** (the browser and Playwright's
   `request` fixture): set `use.proxy` in `playwright.config.ts`, preferably
   in a shared layer or a probe-specific final override layer. `bypass`
   replaces `NO_PROXY`; credentials come from `--environ`:

   ```ts
   use: {
     proxy: {
       server: 'http://proxy.corp:3128',
       bypass: 'localhost,.corp',
       username: process.env.PROXY_USER,
       password: process.env.PROXY_PASSWORD,
     },
   },
   ```

   This covers the browser and the `request` fixture, not plain Node
   `fetch()` in test code. Whether `use.proxy` reaches `--browser lightpanda`
   is unverified.
2. **Everything outside Playwright** — the S3 source/destination (boto3) and
   your own `fetch()`/`http` calls: `--environ HTTPS_PROXY --environ NO_PROXY`
   (and `HTTP_PROXY` if needed). Node ignores proxy variables by default, so
   own `fetch` calls need explicit proxy handling in the test code. Loki keeps
   its dedicated `--loki-proxy`.

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

Before the prompt appears, check_cep builds the check root exactly as a
check run does (all layers merged, archives extracted) and prints
`check root ready: /home/pwuser/tests (<run mode>)`. A merge error
prints its reason and exits 3 without opening a shell. From the shell you can
run Playwright manually:

```bash
cd ~/tests
npx playwright test --reporter=line
```

## 8. Headed Mode — Watch Tests Live on Your Desktop

When a test fails and the HTML report doesn't tell the whole story, you can watch
Playwright drive a real browser window on your desktop. The `--headed` flag
forwards the display connection from the container to your host.

### Prerequisites

- A **Linux desktop session** (KDE Plasma, GNOME, Xfce, etc.)
- **Wayland** (modern default on Fedora, Ubuntu 22.04+, KDE 6): works out of the
  box — `check_cep` auto-detects `WAYLAND_DISPLAY` and mounts the Wayland socket
- **X11**: needs `xhost` installed (usually part of `xorg-x11-server-utils` or
  `x11-xserver-utils`) and the `DISPLAY` variable set

`check_cep` auto-detects which display server is active and configures the
container accordingly. Wayland is preferred when both are available.

### Watch a Test Run

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

> **Tip**: If your test runs too fast to follow, add `slowMo` to your
> `playwright.config.ts` to insert a delay between each Playwright action:
>
> ```typescript
> export default defineConfig({
>   use: {
>     launchOptions: {
>       slowMo: 500,   // 500ms pause between each action
>     },
>   },
> });
> ```

### Interactive Test Development with `--headed --shell`

The most powerful debug workflow: `--headed --shell` drops you into a bash shell
inside the container with the display connection already configured. Your test
directory is mounted at `~/tests` and a visible browser is available. This lets
you run tests manually, re-run individual tests, tweak selectors, and use the
Playwright UI tools — all while watching what happens in the browser.

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
  --timeout 300
```

Once inside the container shell:

```bash
# Run all tests with a visible browser
cd ~/tests
npx playwright test --headed --reporter=line

# Run a single test by name
npx playwright test --headed -g "has title"

# Step-through debugging with Playwright Inspector
# (opens a second window with pause/resume/step controls)
npx playwright test --headed --debug

# Open the Playwright Test Generator (codegen)
# Records your clicks and generates test code automatically
npx playwright codegen https://www.example.com
```

The **Playwright Test Generator** (`codegen`) is especially useful for writing
new tests: it opens a browser and a code panel side by side. As you click
through the website, it records your actions as Playwright test code that you
can copy into a `.test.ts` file.

### How It Works

`check_cep` auto-detects the display server and configures the container:

**Wayland sessions** (modern default):

| Container setting | Purpose |
|-------------------|---------|
| `--volume $XDG_RUNTIME_DIR/wayland-0:…:ro` | Mounts the Wayland compositor socket into the container |
| `--env WAYLAND_DISPLAY=wayland-0` | Tells Chromium where to find the Wayland socket |
| `--env XDG_RUNTIME_DIR=/run/user/1001` | Points to the mounted socket directory |
| `--env PLAYWRIGHT_BROWSER_ARGS=…` | Injects `--enable-features=UseOzonePlatform --ozone-platform=wayland` so Chromium uses native Wayland rendering |

**X11 sessions** (fallback):

| Container setting | Purpose |
|-------------------|---------|
| `--volume /tmp/.X11-unix:/tmp/.X11-unix:ro` | Mounts the X11 unix socket |
| `--env DISPLAY=$DISPLAY` | Tells the browser which X display to connect to |
| `--volume ~/.Xauthority:/tmp/.Xauthority:ro` | X11 authentication cookie (if the file exists) |

Both modes also add:

| Container setting | Purpose |
|-------------------|---------|
| `--userns=keep-id:uid=1001,gid=1001` | Maps your host UID to `pwuser` inside the container, so the process can access the display socket |
| `--security-opt label=disable` | Disables SELinux labeling — the display socket cannot use `:z` relabeling since it's shared with the host |
| `--ipc=host` | Shares the host IPC namespace — Chromium uses MIT-SHM for fast rendering |

> **Note on Chromium vs Chrome**: The browser you see is **Chromium** (blue icon),
> not Google Chrome (multicolor icon). Playwright bundles its own Chromium build —
> it does not use your system browser. This is by design and ensures consistent
> test behavior.

### Browser Args Injection

When `PLAYWRIGHT_BROWSER_ARGS` is set by the host (e.g. with the Wayland Ozone
flags), the container generates a thin config wrapper (`_headed_config.ts` in the
results directory) that extends the user's `playwright.config.ts` and appends the
extra Chromium launch arguments. This means your test configs do not need any
display-specific flags — the container handles it transparently.

### File Ownership in Headed Mode

In headed mode, `--userns=keep-id` maps your host UID directly to `pwuser`
inside the container. Files written by `pwuser` already appear on the host with
your ownership — no `chown` needed. This differs from normal (headless) mode
where `chown root:root` inside the container transfers ownership to the host
user (see [File Ownership](#5-file-ownership-in-local-mode)).

### VNC Fallback for Wayland + Vision Tests (`--vnc`)

On most desktops `--headed` is all you need: the browser window opens natively on
your Wayland or X11 session. There is one exception:

> **Wayland + vision image-matching tests**
>
> When `--headed` forwards the Wayland socket into the container, Chromium
> activates its `--ozone-platform=wayland` compositing pipeline. That pipeline
> produces slightly different pixel values in CDP screenshots (`page.screenshot()`)
> compared to headless mode. Vision tests compare against reference images
> captured headlessly, so the pixel difference causes them to fail even though
> the test logic is correct.

The `--vnc` flag is the workaround. Instead of forwarding the host's Wayland
socket, the container starts an internal Xtigervnc server (X11 + VNC in one
process) and Chromium connects to it. Because Chromium uses the X11 rendering
path, CDP screenshots match the headless reference images and vision tests pass.
The container publishes the VNC server on `127.0.0.1:5900`; connect to it with
a VNC viewer on the host to watch the browser.

```bash
# 1. Start the test with --vnc  (the hint appears on stderr)
python3 src/check_cep \
  --headed --vnc \
  --host-name testhost \
  --service-description Consol_Homepage \
  --image localhost/check_cep:latest \
  --probe-location local \
  --test-source local \
  --result-dest local \
  --test-dir /tmp/my-first-test \
  --result-dir /tmp/my-first-results \
  --timeout 60

# 2. In a second terminal, connect to the VNC server
vncviewer SecurityTypes=None 127.0.0.1::5900
```

`check_cep` prints `VNC: connect with: vncviewer SecurityTypes=None 127.0.0.1::5900`
to stderr before the container starts, so you know when to connect. Xtigervnc
takes about 4 seconds to start; the VNC viewer may need to reconnect once.

**When to use `--headed` vs `--headed --vnc`:**

| Situation | Use |
|-----------|-----|
| Debugging any test on Wayland or X11 | `--headed` |
| Vision tests on Wayland (screenshots must match headless) | `--headed --vnc` |
| Interactive shell (`--shell`) | `--headed --shell` (VNC not supported with `--shell`) |
| X11 desktop (no Wayland) | `--headed` (VNC unnecessary) |

**Host requirement**: `tigervnc` must be installed for the VNC viewer
(`dnf install tigervnc` on Fedora, `apt install tigervnc-viewer` on Debian/Ubuntu).
The container already includes `tigervnc-standalone-server`.

### Error Messages

If the environment doesn't support headed mode, `check_cep` exits UNKNOWN:

| Message | Fix |
|---------|-----|
| `--headed requires WAYLAND_DISPLAY or DISPLAY to be set` | Run from a desktop terminal, not an SSH session |
| `--headed: X11 socket /tmp/.X11-unix/X0 not found` | Your X server isn't running; log in to a graphical desktop |
| `--headed requires xhost to be installed (X11 mode)` | Install `xorg-x11-server-utils` (Fedora) or `x11-xserver-utils` (Debian) |
| `crun: make '…/overlay/…/merged' private: Permission denied` | Directory traverse bit missing on the site home — see below |

### Permission denied making overlay merged private

`--headed`, `--vnc`, and `--authoring` add `--userns=keep-id` so the container
user maps to the site user on the host (display sockets, writable authoring
workspace). Headless scheduled checks do **not** use keep-id and are unaffected.

With keep-id, the container's root is a **subordinate UID** from `/etc/subuid`.
That UID must walk from `/` to Podman's overlay store:

```text
$OMD_ROOT/.local/share/containers/storage/overlay/<id>/merged
```

OMD site homes are typically mode `750` (group-executable, not world) and
Podman creates `.local/share/containers/…` as `700`. Neither grants `x` to
*other*, so the subuid cannot enter the path. `crun` then fails before the
container starts:

```text
Error: crun: make `$OMD_ROOT/.local/share/containers/storage/overlay/…/merged` private: Permission denied: OCI permission denied
```

Typical companion signs: Nagios `CRITICAL`, `'duration'=0s`,
`'podman_metric_collection_failed'=1`. The Playwright test never ran.

**Confirm** (as the site user):

```bash
namei -l "$OMD_ROOT/.local/share/containers/storage"
stat -c '%a %n' "$OMD_ROOT" "$OMD_ROOT/.local" \
  "$OMD_ROOT/.local/share" \
  "$OMD_ROOT/.local/share/containers" \
  "$OMD_ROOT/.local/share/containers/storage"
```

A last digit of `0` on any of those directories (no execute for other) is the
problem. `750` on `$OMD_ROOT` is the same hole: the site group can traverse,
the subuid is not in that group.

Many sites keep `$OMD_ROOT` at `700` or `750` **on purpose**. You do not have
to open it to the world. Pick one of the following; they all satisfy the
subuid traverse without making the site world-readable.

**Option A (preferred) — move rootless storage off the site home.**
Podman has no switch that turns keep-id's subuid walk off, but it *does*
let you put the overlay store on a path that is already traversable (the
usual reason `rootless_storage_path` exists is NFS homes; it works here
too). As the site user:

```bash
mkdir -p ~/.config/containers /var/tmp/containers-$USER
cat > ~/.config/containers/storage.conf <<EOF
[storage]
driver = "overlay"
graphroot = "/var/tmp/containers-$USER/storage"
EOF
# existing images live under $OMD_ROOT/.local/share/containers — either
# `podman system reset` (wipes them) or copy that tree to the new graphroot
podman info --format '{{.Store.GraphRoot}}'   # must print /var/tmp/…
```

`/var/tmp` is typically `1777`, so the subuid can walk to the new store.
`$OMD_ROOT` can stay `700`/`750`. Headless scheduled checks keep working;
`--headed`/`--vnc`/`--authoring` now look at the new graphroot.

**Option B — POSIX ACL for the one subuid, site mode unchanged.**
Container root is the *first* ID in the site user's `/etc/subuid` range.
Grant that UID execute on the path; `other` stays without `x`:

```bash
SUBUID=$(awk -F: -v u="$(id -un)" '$1==u {print $2; exit}' /etc/subuid)
# filesystem must be mounted with the `acl` option (ext4/xfs usually are)
setfacl -m "u:${SUBUID}:--x" \
  "$OMD_ROOT" "$OMD_ROOT/.local" "$OMD_ROOT/.local/share" \
  "$OMD_ROOT/.local/share/containers" \
  "$OMD_ROOT/.local/share/containers/storage"
# so overlay dirs Podman creates later inherit the ACE:
setfacl -d -m "u:${SUBUID}:--x" \
  "$OMD_ROOT/.local/share/containers/storage"
getfacl "$OMD_ROOT"   # unix mode still 750; extra user:${SUBUID}:--x
```

`stat` will still show `750`/`700`; `getfacl` shows the extra ACE. This is
not world-readable.

**Option C — `chmod o+x` on the chain** if policy allows execute-for-other
(not write, not `777`):

```bash
chmod o+x "$OMD_ROOT" \
          "$OMD_ROOT/.local" \
          "$OMD_ROOT/.local/share" \
          "$OMD_ROOT/.local/share/containers" \
          "$OMD_ROOT/.local/share/containers/storage"
```

If `/omd/sites/<site>` and `/opt/omd/sites/<site>` are distinct directories
(not a symlink), apply the same change on the real path too.

`fuse-overlayfs` (`mount_program` in `storage.conf`) does **not** remove
the need to traverse to the overlay dir; `skip_mount_home` skips a
different mount (the storage home), not crun's `make-private` on `merged`.

After A, B, or C:

```bash
podman run --rm --userns=keep-id:uid=1001,gid=1001 localhost/check_cep:latest true
```

Silence and exit 0 means the overlay is reachable; re-run the headed/VNC
or authoring command.

Why the subuid must traverse at all is in
[Appendix A §4](#4-keep-id-and-directory-traverse-bits).

### When to Use Headed Mode (and When Not To)

**Good uses:**
- Debugging a flaky test — watch what happens visually
- Writing a new test — iterate with `--headed --shell` and `playwright codegen`
- Investigating timing issues — see if the page loaded before the assertion ran
- Step-through debugging with Playwright Inspector (`--debug`)
- Cookie consent banners and popups — see what's blocking your selectors

**Not appropriate for:**
- Production monitoring (headless is the default for a reason)
- CI pipelines (no display)
- Automated test runs (adds overhead and requires a desktop session)

> **Next step — writing your own tests**: For advanced test authoring
> including the `check-cep-vision` API, persistent template images,
> regions, click offsets, and choosing between DOM and vision selectors,
> see [WRITING-TESTS.md](WRITING-TESTS.md).

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
| `--test-artifact` | `$OMD_ROOT/etc/check_cep/tests/%h/%s` | Test layer: directory or `.tgz`/`.tar.gz` (local), `/bucket/key.tgz` (S3). Repeatable for local sources; merged in order, later wins. Supports `%h`/`%s`. See [Layers](#layers) |
| `--test-dir` | — | Deprecated single test directory (supports `%h`/`%s`); mutually exclusive with `--test-artifact` |
| `--environ NAME[=VALUE]` | — | Pass an environment variable to the test container in every mode (repeatable). Values are masked as `***` in the output. See [Secrets](#6-secrets-and---environ) |
| `--result-dir` | `$OMD_ROOT/var/tmp/check_cep/%h/%s` | Host-side result directory. Supports `%h` (hostname), `%s` (service), `%t` (Unix epoch of process start — creates a new directory per run) |
| `--report-retention` | off | Delete run directories older than this duration after each run (e.g. `24h`, `168h`). Requires `%t` in `--result-dir`. |
| `--timeout` | `60` | Container timeout in seconds |
| `--memory-limit` | `2g` | Container memory limit |
| `--debug` | off | Verbose logging |
| `--shell` | off | Interactive bash shell |
| `--headed` | off | Headed browser on your desktop (Wayland/X11 auto-detected, debug only) |
| `--vnc` | off | VNC fallback for headed mode — use with `--headed` on Wayland when vision tests must match headless references (see [VNC Fallback](#vnc-fallback-for-wayland--vision-tests---vnc)) |

### Performance Data

Each successful run produces by default these metrics in the Nagios perfdata:

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

Using Playwright's `test.step()` to group actions in your test produces
additional per-step duration metrics automatically.  See
[WRITING-TESTS.md](WRITING-TESTS.md#structuring-tests-with-teststep)
for details.

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
make image-ai      # Build the AI-enhanced image (localhost/check_cep:ai-latest) —
                    # required for AI-assisted test authoring, see below
make test-image-ai # Build the AI-enhanced test image (check_cep:test-ai)
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

### Spectate Mode — Watch the Tests Live on Screen

Set `CEP_SPECTATE=1` to run the integration tests with visible browsers
on your desktop.  Every Playwright action is slowed down, and vision
highlight boxes linger so you can follow what is happening.

This requires a working X11 or Wayland display — either a local desktop
session or SSH with X11 forwarding (`ssh -X`).

```bash
# The nicest show — just the vision tests
CEP_SPECTATE=1 pytest tests/integration/test_modes.py -k "tc_vision and local" -v

# All local tests
CEP_SPECTATE=1 pytest tests/integration/test_modes.py -k local -v
```

You can tune the speed with environment variables:

```bash
# Slower — more time to watch each step
CEP_SLOW_MO=800 CEP_VISION_HIGHLIGHT_MS=3000 CEP_SPECTATE=1 pytest tests/integration/test_modes.py -k "tc_vision and local" -v

# Faster — just a quick glance
CEP_SLOW_MO=200 CEP_VISION_HIGHLIGHT_MS=1000 CEP_SPECTATE=1 pytest tests/integration/test_modes.py -k "tc_vision and local" -v
```

| Variable | Default (spectate) | Effect |
|----------|-------------------|--------|
| `CEP_SLOW_MO` | 400 | Milliseconds Playwright pauses between each action |
| `CEP_VISION_HIGHLIGHT_MS` | 2000 | How long the vision highlight box stays visible |
| `CEP_VNC` | (unset) | When set alongside `CEP_SPECTATE=1`, injects `--vnc` so the container uses Xtigervnc instead of forwarding the host display. Required on Wayland to keep vision tests passing. |

On a Wayland desktop, use `CEP_VNC=1` together with `CEP_SPECTATE=1`:

```bash
# Wayland: vision tests + spectate mode — connect manually with vncviewer
CEP_SPECTATE=1 CEP_VNC=1 pytest tests/integration/test_modes.py -k "tc_vision and local" -v
```

When `CEP_VNC=1` is set, `check_cep` prints the vncviewer connect command to
stderr. Open a second terminal and run it to watch the browser.

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

---

## Appendix A — Rootless Podman Internals

Three separate Linux subsystems must cooperate for rootless Podman to work
correctly as an OMD site user. Each prerequisite fixes a failure in a different
layer of the stack.

### 1. User namespaces and subordinate ID maps

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

### 2. Systemd linger and the user session unit

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

### 3. Cgroup controller delegation and io.stat

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

### 4. keep-id and directory traverse bits

`--headed`, `--vnc`, and `--authoring` pass `--userns=keep-id:uid=1001,gid=1001`.
That maps the host site user to `pwuser` (uid 1001) inside the container, and
maps **container root** to the first subordinate UID from `/etc/subuid`.

`crun` then has to `mount --make-private` the overlay `merged` directory under
`$OMD_ROOT/.local/share/containers/storage/`. The process doing that mount is
the subuid, not the site user. Linux directory traverse (`x`) is required on
every path component from `/` down to that store.

A site home of `750` (`rwxr-x---`) lets the site *group* through and blocks
everyone else. Podman's default `700` on `.local/share/containers/…` blocks
even the group. The subuid is in neither set, so the mount fails with
`OCI permission denied` and the container never starts.

There is no Podman/check_cep flag that disables this walk: keep-id *means*
container root is a subuid. What you can change is **where** the overlay
lives, or **who** may traverse there:

- relocate `graphroot` / `rootless_storage_path` off `$OMD_ROOT` (preferred
  when the site home must stay `700`/`750`);
- POSIX ACL `u:<first-subuid>:--x` on the path (`setfacl`), unix mode
  unchanged;
- or `chmod o+x` on the chain if policy allows execute-for-other.

The operator-facing steps live under
[Permission denied making overlay merged private](#permission-denied-making-overlay-merged-private).
