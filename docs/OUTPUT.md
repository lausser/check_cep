# Output and Logging Architecture

This document describes the output system of check_cep: every place that
produces visible output, how the layers interact, and the exact rules for what
is shown in normal mode vs `--debug` mode.

It serves as documentation of the current state.

---

## Design Principles

1. **Operator-first**: Without `--debug` the long output shows exactly what a
   monitoring operator needs — test progress, errors, and any intentional
   `console.log` from the test author. Nothing more.
2. **Debug reveals internals**: With `--debug` the same output is augmented
   with vision-internal decision traces, container orchestration details, and
   any explicit `cepDebug()` calls from test code.
3. **Single prefix, single filtering point**: Debug-level lines use the prefix
   `[CEPDBG]` on stdout. They flow through the entire pipeline untouched and
   are included or excluded by a single check on the host side in
   `extract_output_from_steps()`.
4. **stderr means real errors**: Only genuine errors from Playwright or
   Node.js appear on stderr. No infrastructure debug traces pollute stderr,
   so `has_stderr` reliably triggers WARNING status.

---

## Overview: Two Processes, Three Layers

```
┌─── Host (src/check_cep) ──────────────────────────────────────────────┐
│                                                                       │
│  1. Python logging module  (logger.debug / logger.warning)            │
│  2. Nagios status line     (print via nagios_exit)                    │
│  3. Container stdout/stderr capture → "long output"                   │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
        ▲ captures stdout + stderr from:
┌─── Container (src/container/) ────────────────────────────────────────┐
│                                                                       │
│  4. run.py Python logging  (logger.debug / print)                     │
│  5. run.py marker lines    (PWTIMEOUT_EXCEEDED, S3UPLOADHASFAILED,    │
│                              LOKIERROR, PLAYWRIGHTCHECKDURATIONFORPLUGIN)│
│  6. check-cep-helpers      (console.log → stdout)  [CEP+1234ms]      │
│  7. check-cep-vision       (console.log → stdout)  [CEPDBG] ...      │
│  8. Playwright line reporter (stdout)                                 │
│  9. Test code console.log  (captured in steps.json stdout)            │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Prefixes and Their Meaning

There are exactly three prefixes in the system. Each has a clear purpose and
visibility rule:

| Prefix | Source | Channel | Visible | Purpose |
|--------|--------|---------|---------|---------|
| `[CEP+Nms]` | check-cep-helpers | `console.log` (stdout) | Always | Operator-facing test progress trace |
| `[CEPDBG]` | check-cep-vision, `cepDebug()` | `console.log` (stdout) | `--debug` only | Internal decision traces, developer diagnostics |
| *(no prefix)* | test code `console.log` | `console.log` (stdout) | Always | Anything the test author intentionally prints |

Additional host-side prefixes (not from the container):

| Prefix | Source | Visible | Purpose |
|--------|--------|---------|---------|
| `YYYY-MM-DD HH:MM:SS - DEBUG -` | host check_cep Python logging | `--debug` only | Host orchestration (podman command, PID ops) |
| `__Stdout__`, `__Stderr__`, `__Errors__` | host check_cep | Always | Section headers in parsed long output |

---

## Layer-by-Layer Detail

### 1. Host-side Python logging (`src/check_cep`)

**Module**: `logging.getLogger("check_cep")`

**Format**: `2026-03-17 19:50:12,091 - DEBUG - <message>`

**Configuration** (in `main()`):
- Without `--debug`: level `CRITICAL` — effectively silent.
- With `--debug`: level `DEBUG`, messages go to:
  - `$OMD_ROOT/var/log/check_cep.log` (rotating file handler, always)
  - stderr (console handler, only when `--debug`)

**What it logs**:
- The full `podman run` command line
- PID file operations (stale PID detection, cleanup warnings)
- Auth retry attempts
- steps.json parse failures

**Visible to user**: Only with `--debug`. Appears as timestamped lines *before*
the Nagios status line:

```
2026-03-17 19:50:12,091 - DEBUG - running command: /usr/bin/podman run --rm ...
OK - test Consol_Homepage succeeded | ...
```

### 2. Nagios status line

**Function**: `nagios_exit(status, message, perfdata_str, long_output)`

**Always printed**, regardless of `--debug`. This is the primary output:

```
OK - test Consol_Homepage succeeded | 'TestDuration'=22402ms 'duration'=28s ...
```

Followed by the "long output" (container output, see layer 3).

### 3. Container output (long output block)

The host captures everything the container writes to stdout/stderr during
`podman run`. After the container exits, this captured text is processed:

1. If `steps.json` exists: output is extracted from its `stdout`, `stderr`,
   and `errors` arrays (function `extract_output_from_steps`).
2. If `steps.json` is missing: raw captured stdout + stderr is used as-is.

The result is printed as "long output" below the Nagios status line.

**Sections in the long output** (prefixed by double-underscore markers):
- `__Stdout  - <test name>__` — test stdout from steps.json
- `__Stderr  - <test name>__` — real test stderr (triggers WARNING)
- `__Errors  - <test name>__` — Playwright error messages from steps.json

If the container produced no parseable output, the text `NO CONTAINER OUTPUT`
is printed.

**`[CEPDBG]` filtering** — When `extract_output_from_steps` processes stdout
entries from steps.json, lines starting with `[CEPDBG]` are:
- **included** if `--debug` was passed
- **excluded** otherwise

This is the single point where debug-level output is gated. No other
filtering exists anywhere in the pipeline.

### 4. Container-side Python logging (`run.py`)

**Module**: `logging.getLogger("run.py")`

**Configuration**:
- `DEBUG` env var set (passed when host uses `--debug`): `level=DEBUG`
- Otherwise: `level=INFO`

**What it logs**:
- Test file discovery (`Found test file: ...`)
- Playwright command line (`Running: timeout 70 npx playwright test ...`)
- Config wrapper generation for spectate mode
- Lightpanda CDP lifecycle
- Plugin operations (S3 uploads, Loki shipping, ownership fixup)

**Note**: These messages go to the container's stderr. They are **not**
captured in steps.json. The host only shows raw stderr as long output when
steps.json is missing.

`run.py` forwards all Playwright stdout and stderr unchanged. All
content-based filtering happens on the host side.

### 5. Container-side marker lines (`run.py` print statements)

Protocol markers that `run.py` prints to stdout. The host scans for them:

| Marker | Meaning | Detected by |
|--------|---------|-------------|
| `PWTIMEOUT_EXCEEDED` | coreutils `timeout` killed Playwright | `check_timeout()` |
| `S3UPLOADHASFAILED [[[...]]]` | S3 result upload failed | `check_s3_upload_failure()` |
| `LOKIERROR [[[...]]]` | Loki log shipping failed | regex in main |
| `PLAYWRIGHTCHECKDURATIONFORPLUGIN=<int>` | Playwright wall-clock duration | parsed for duration |
| `UNKNOWN: ...` | Plugin load / test acquisition errors | causes exit 3 |

These markers are **always** printed and are consumed by the host-side parsing
logic — never shown to the user directly.

### 6. check-cep-helpers (`console.log` → stdout)

**Module**: `src/container/check-cep-helpers/index.js`

**Always-visible functions** (prefix `[CEP+<elapsed>ms]`):
- `cepLog(message)` — generic log
- `cepLogLocated(target)` — "located element: ..."
- `cepLogFound(value)` — "located string: ..."
- `cepLogType(target, value)` — "typing string into ..."
- `cepLogPress(target)` — "pressing button/link/option: ..."
- `cepLogWait(durationMs, reason)` — "waiting Nms ..."
- `cepLogUrl(page)` — "current page url is ..."

**Debug-only function** (prefix `[CEPDBG]`):
- `cepDebug(message)` — developer diagnostic output, only shown with `--debug`

All functions use `console.log` (stdout). Playwright captures them in
steps.json `stdout` arrays.

**Example output** (always visible):
```
[CEP+3123ms] navigated to start page
[CEP+3123ms] current page url is https://...
[CEP+5127ms] Starting cookie consent handling...
```

**Example output** (debug only, from `cepDebug`):
```
[CEPDBG] custom diagnostic from test author
```

Test authors call these functions explicitly in `.test.ts` files.

### 7. check-cep-vision (`console.log` → stdout)

**Module**: `src/container/check-cep-vision/index.js`

**Prefix**: `[CEPDBG]`

**Channel**: `console.log` → Playwright captures in `steps.json` `stdout`.

All 75 trace calls use `console.log('[CEPDBG] ...')`, captured in
steps.json `stdout` and visible only with `--debug`. Vision traces do not
pollute stderr.

**What it logs** (examples of the 75 call sites):

Image matching:
- `[CEPDBG] locateByImage called: template=vorname.png`
- `[CEPDBG] locateByImage result: reason=found score=0.9523`
- `[CEPDBG] waitForImage succeeded: template=vorname.png elapsed=3200ms`
- `[CEPDBG] waitForImage failed (timeout): reason=no_match elapsed=5000ms`
- `[CEPDBG] existsByImage result: true`

Best-effort interaction strategies:
- `[CEPDBG] clickBestEffort called`
- `[CEPDBG] clickBestEffort click: succeeded`
- `[CEPDBG] clickBestEffort click: failed (element not visible)`
- `[CEPDBG] clickBestEffort click({force}): succeeded`
- `[CEPDBG] typeBestEffort click+type: succeeded`
- `[CEPDBG] fillBestEffort fill: failed (strict mode violation)`
- `[CEPDBG] fillBestEffort evaluate(focus+value+events): succeeded`

Hybrid DOM/vision fallback:
- `[CEPDBG] typeByImageOr called: template=vorname.png selectors=2`
- `[CEPDBG] typeByImageOr succeeded: strategy=vision`
- `[CEPDBG] typeByImageOr vision failed: no match, falling back to DOM`
- `[CEPDBG] typeByImageOr succeeded: strategy=dom`
- `[CEPDBG] clickByImageOr skipping vision (no visual browser), using DOM fallback`

Scroll/preparation:
- `[CEPDBG] prepareTarget scroll: attempting`
- `[CEPDBG] prepareTarget scroll: succeeded`

Highlighting:
- `[CEPDBG] highlightByImage called: template=logo.png`
- `[CEPDBG] highlightByImage succeeded`

### 8. Playwright line reporter (stdout)

Playwright's built-in `line` reporter writes to stdout:

```
Running 1 test using 1 worker
  ✓  1 [chromium] > tests/consol.test.ts:4:5 > consol.de has... (5s)
  1 passed (6s)
```

This is **not** captured in steps.json. It goes to raw container stdout
and is typically invisible — the host prefers steps.json. It only surfaces
when steps.json is missing (syntax error, crash).

### 9. Test code `console.log` (in steps.json)

Any `console.log()` in test code that is not from check-cep-helpers or
check-cep-vision also ends up in steps.json stdout arrays. Lines starting
with `NagiosPerfData:` are parsed for custom performance data and excluded
from the text output. All other lines are shown in the long output.

---

## Comparison: Normal vs `--debug`

| Output element | Normal | `--debug` |
|----------------|--------|-----------|
| Host Python logging (podman cmd, PID ops) | Hidden | Printed to stderr + log file |
| Nagios status line + perfdata | Printed | Printed |
| `[CEP+Nms]` lines (check-cep-helpers) | Printed | Printed |
| Test author `console.log` (no prefix) | Printed | Printed |
| `[CEPDBG]` lines (vision + cepDebug) | **Excluded** | **Included** |
| `__Stderr__` section (real errors) | Printed (triggers WARNING) | Printed (triggers WARNING) |
| `__Errors__` section (Playwright errors) | Printed | Printed |
| run.py Python logging | Not in steps.json, not shown | Not in steps.json, not shown |
| Marker lines (PWTIMEOUT, S3UPLOAD, etc.) | Consumed by host, not shown | Consumed by host, not shown |
| Playwright line reporter | Not in steps.json, not shown | Not in steps.json, not shown |

### Example: Normal output

```
OK - test Consol_Homepage succeeded | 'TestDuration'=22402ms 'duration'=28s ...
__Stdout  - In-Kontakt-bleiben migrated from Sakuli__
[CEP+3127ms] navigated to start page
[CEP+3127ms] current page url is https://www.mannheimer.de/oldtimer
[CEP+3127ms] waiting 2000ms before first interaction
[CEP+10083ms] Starting cookie consent handling...
[CEP+12713ms] No active cookie banner detected
[CEP+12713ms] located element: link/button "Jetzt anfordern"
[CEP+12713ms] pressing button/link/option: Jetzt anfordern
[CEP+25999ms] located element: field near image template "vorname.png"
[CEP+25999ms] typing string into field "Vorname": icinga
```

### Example: Debug output (same test)

```
2026-03-17 19:52:34,498 - DEBUG - running command: /usr/bin/podman run --rm ...
OK - test Consol_Homepage succeeded | 'TestDuration'=22402ms 'duration'=28s ...
__Stdout  - In-Kontakt-bleiben migrated from Sakuli__
[CEP+3127ms] navigated to start page
[CEP+3127ms] current page url is https://www.mannheimer.de/oldtimer
[CEP+3127ms] waiting 2000ms before first interaction
[CEP+10083ms] Starting cookie consent handling...
[CEP+12713ms] No active cookie banner detected
[CEP+12713ms] located element: link/button "Jetzt anfordern"
[CEP+12713ms] pressing button/link/option: Jetzt anfordern
[CEPDBG] typeByImageOr called: template=vorname.png selectors=2
[CEPDBG] locateByImage called: template=vorname.png
[CEPDBG] locateByImage result: reason=found score=0.9523
[CEPDBG] typeByImageOr succeeded: strategy=vision
[CEP+25999ms] located element: field near image template "vorname.png"
[CEP+25999ms] typing string into field "Vorname": icinga
```

---

## Output Flow Diagram (Target State)

```
Test .ts file
  │
  ├── cepLog("message")            ──► console.log ──► steps.json stdout
  │   cepLogLocated(), etc.             prefix: [CEP+Nms]
  │                                     ──► ALWAYS shown in long output
  │
  ├── cepDebug("message")          ──► console.log ──► steps.json stdout
  │   (from check-cep-helpers)          prefix: [CEPDBG]
  │                                     ──► shown only with --debug
  │
  ├── vision internal traces        ──► console.log ──► steps.json stdout
  │   (from check-cep-vision)           prefix: [CEPDBG]
  │                                     ──► shown only with --debug
  │
  ├── console.log("custom")        ──► steps.json stdout
  │   (test author, no prefix)          ──► ALWAYS shown in long output
  │
  ├── real stderr (Node/PW errors) ──► steps.json stderr
  │                                     ──► ALWAYS shown (triggers WARNING)
  │
  └── Playwright assertions        ──► steps.json errors
                                        ──► ALWAYS shown in long output

run.py
  │
  ├── logger.debug("...")          ──► container stderr (not in steps.json)
  │                                     ──► NOT shown in parsed output
  │
  └── print("MARKER...")           ──► container stdout
                                        ──► consumed by host pattern matching

check_cep (host)
  │
  ├── logger.debug("...")          ──► stderr (--debug only)
  │
  └── nagios_exit(...)             ──► stdout (always)
       ├── line 1: status | perfdata
       └── lines 2+: long output
            ├── [CEP+Nms] lines     (always)
            ├── console.log lines   (always)
            ├── [CEPDBG] lines      (--debug only)
            ├── __Stderr__ section  (always, if present)
            └── __Errors__ section  (always, if present)
```

