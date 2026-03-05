# check_cep Tutorial

This tutorial walks you through building the container image, writing your first
Playwright test, and running it with `check_cep`.

## Prerequisites

- **Podman** installed and working (rootless mode is fine)
- **Python 3** on the host (for `check_cep` itself)
- Internet access (to pull the base image and for tests to reach target websites)

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

## 8. OMD Integration

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

## 9. CLI Reference

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
