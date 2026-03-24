# Lessons Learned

## Spectate Mode on Wayland: Vision Test Failures and the VNC Workaround

**Context**: `CEP_SPECTATE=1` runs Playwright in headed mode (`--headed`) so a human
can watch the browser during test execution. On two X11 desktops this worked fine. On
a Wayland laptop the same vision image-matching tests started failing — same test code,
same reference images, different machine.

---

### 1. Root cause: `--ozone-platform=wayland` changes CDP screenshot pixel values

**What happens step by step**:

1. The host has `WAYLAND_DISPLAY=wayland-0` set in its environment.
2. `check_cep` detects Wayland and forwards the compositor socket into the container:
   `--volume $XDG_RUNTIME_DIR/wayland-0:…:ro` + `--env WAYLAND_DISPLAY=wayland-0`.
3. Inside the container, `chrome-wrapper` sees `WAYLAND_DISPLAY` set and appends
   `--enable-features=UseOzonePlatform --ozone-platform=wayland` to every Chromium
   invocation.
4. Chromium switches from the default X11/headless compositing pipeline to the
   **Ozone/Wayland** pipeline.
5. Playwright's `page.screenshot()` is a CDP call (`Page.captureScreenshot`). The
   screenshot is captured **inside** Chromium by the same compositor that renders the
   page. With the Ozone/Wayland pipeline active, the compositor produces slightly
   different pixel values — the same elements are at the same positions, but the
   luminance channel differs. A typical signature: gray-channel score `0.7813` instead
   of the expected `≥0.96`.
6. Vision tests compare against reference images captured **headlessly** (no Wayland,
   no Ozone). The pixel difference exceeds the matching threshold and the test fails.

**Why it only failed on the laptop**: The other two machines ran X11. Without
`WAYLAND_DISPLAY`, `chrome-wrapper` never added `--ozone-platform=wayland`, so
Chromium stayed on the X11/headless rendering path.

**Key insight**: The problem is not in the test logic or the reference images. It is in
the rendering pipeline that produces the pixels that Playwright's screenshot captures.
Headless Chromium and X11-headed Chromium produce screenshots close enough to match
references. Wayland-headed Chromium does not.

---

### 2. Non-solutions that were tried and abandoned

#### 2a. `LIBGL_ALWAYS_SOFTWARE=1`

Passed through to the container as an env var. Has no effect on Chromium. Chromium uses
ANGLE as its graphics abstraction layer, not Mesa/libGL. `LIBGL_ALWAYS_SOFTWARE` only
affects Mesa-based OpenGL applications. **Abandoned.**

#### 2b. `--font-render-hinting=none` in `chrome-wrapper`

Added to the Wayland branch. Thought to affect subpixel rendering which could shift
pixel values. Scores were identical (`gray=0.7813` unchanged). Font hinting affects text
rendering, not the compositing pipeline that produces CDP screenshots. **Abandoned.**

#### 2c. Forwarding XWayland socket to the container (X11 display path)

The ideal fix: give the container `DISPLAY=:0` (the XWayland display) instead of
`WAYLAND_DISPLAY`. Chromium would use X11 rendering, screenshots would match.

Implementation: change `detect_display_server()` to return `x11` preferentially on
Wayland systems by checking `DISPLAY` before `WAYLAND_DISPLAY`.

**Blocker**: SELinux on Fedora. The container's SELinux type (`spc_t`) cannot connect
to XWayland's Unix domain socket (`user_tmp_t`). The connection is refused even after
`xhost +`. The container starts, Playwright launches, then hangs indefinitely waiting
for Chromium to appear — no error message, just silence. **Abandoned.** Do not retry
this approach without a custom SELinux policy or `--security-opt label=disable`.

---

### 3. The solution: Xtigervnc inside the container

Instead of forwarding a display from the host into the container, the container creates
its own X11 display internally using **Xtigervnc** (`tigervnc-standalone-server`).

**Why Xtigervnc and not Xvfb**:

| Option | Problem |
|--------|---------|
| `Xvfb` alone | Virtual framebuffer, but no built-in way to view it from outside the container. Adding `x11vnc` to read the framebuffer requires MIT-SHM (XSHM), which is blocked in rootless Podman containers. Result: permanent black screen in the VNC viewer. |
| `Xvfb` + `x11vnc` | `x11vnc` uses the MIT-SHM X extension to read the Xvfb framebuffer. Rootless Podman does not expose `CLONE_NEWIPC` to the container, so shared memory IPC is unavailable. `x11vnc` connects but shows a black screen. |
| `Xtigervnc` | A combined X server + VNC server in a single process. It **owns** the framebuffer directly — no XSHM, no inter-process framebuffer reading. Works in rootless Podman. |

**Full flow**:

1. `check_cep` on the host detects `--vnc` flag.
2. Podman command gets `--publish 127.0.0.1:5900:5900` instead of Wayland socket
   forwarding.
3. `check_cep` prints to stderr: `VNC: connect with: vncviewer SecurityTypes=None 127.0.0.1::5900`.
4. Inside the container, `run.py` sees `HEADED=1` and no `DISPLAY` or `WAYLAND_DISPLAY`.
5. `run.py` starts Xtigervnc on display `:1`, port 5900, no password.
6. After a 4-second startup delay, `run.py` sets `DISPLAY=:1` and starts Playwright.
7. Playwright launches Chromium. `chrome-wrapper` sees `DISPLAY=:1` set and
   `WAYLAND_DISPLAY` not set — uses the **X11 lighter flags** branch (no `--disable-gpu`,
   no `--ozone-platform`).
8. Chromium renders on the Xtigervnc X11 display. CDP screenshots use the X11/headless
   rendering path. Vision tests pass.
9. The human spectator connects with `vncviewer` and watches the browser in the VNC
   window.

---

### 4. `--disable-gpu` makes Chromium paint a black window in a virtual X display

Early in development the X11 branch of `chrome-wrapper` included `--disable-gpu`. The
VNC window showed a browser window outline with a black content area.

**Cause**: `--disable-gpu` disables the GPU compositor entirely. The GPU compositor is
what blits the rendered page pixels onto the X window surface. Without it, the X window
exists (title bar, decorations) but the content never reaches the screen.

**Fix**: Remove `--disable-gpu` from the X11 branch. Keep `--use-gl=swiftshader` to
ensure software-only rendering (no real GPU needed in the container). SwiftShader
provides a software GL implementation that the compositor uses to render the page
without hardware.

Also remove `--disable-gpu-compositing` and `--disable-gpu-rasterization` from the X11
branch for the same reason — these flags suppress the compositor steps that paint to
the X surface.

**Final X11 branch flags** (the headless/default branch keeps `--disable-gpu`):
```bash
if [ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  EXTRA=(
    --disable-dev-shm-usage
    --disable-accelerated-2d-canvas
    --disable-accelerated-video-decode
    --disable-accelerated-video-encode
    --use-gl=swiftshader
  )
fi
```

---

### 5. `XAUTHORITY` is not at `~/.Xauthority` on Wayland systems

When `check_cep` forwards X11 credentials in headed mode (X11 path), it mounts the
Xauthority file into the container. The code originally hardcoded `~/.Xauthority`.

On Wayland desktops, the Xauthority file lives under `$XDG_RUNTIME_DIR`, e.g.
`/run/user/1000/xauth_fqaZus`. The hardcoded path does not exist and the X auth
handshake fails silently (the socket mounts successfully but Chromium is refused).

**Fix**:
```python
xauthority = os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
```

---

### 6. TigerVNC viewer parameter syntax

TigerVNC's `vncviewer` uses a non-standard parameter style: no leading dash, `=` separator,
**plural** form:

```bash
# Correct
vncviewer SecurityTypes=None 127.0.0.1::5900

# Wrong — silently ignored, viewer prompts for password and fails
vncviewer -SecurityType None 127.0.0.1::5900
```

The `-SecurityType None` form (dash, singular, space) is accepted by the argument parser
but not applied — the viewer proceeds with its default security mode (password required).
The correct form is `SecurityTypes=None` (no dash, plural, equals).

---

### 7. Design decision: `--vnc` is opt-in, not auto-detected

An earlier iteration auto-detected Wayland and silently switched to VNC mode. This was
reverted because:

- **`--headed` works on Wayland** for all non-vision-test purposes. The browser appears
  natively on the desktop. Auto-switching would break this for users who just want to
  watch a test and don't care about screenshot pixel accuracy.
- **The problem is specific to vision tests**: only tests that compare CDP screenshots
  against headless reference images are affected. Other tests pass fine with Wayland
  forwarding.
- **Principle of least surprise**: an opt-in flag (`--vnc`) makes the trade-off explicit.
  The user controls whether to use native Wayland rendering (browser on desktop, vision
  tests may fail) or Xtigervnc rendering (VNC viewer required, vision tests pass).

**Final design**:

| Command | Display path | Vision tests | Browser visible |
|---------|-------------|--------------|-----------------|
| `--headed` on Wayland | Wayland socket → ozone-wayland | May fail | Native window on desktop |
| `--headed --vnc` on Wayland | Xtigervnc (X11) | Pass | VNC viewer window |
| `--headed` on X11 | X11 socket | Pass | Native window on desktop |

In the integration test harness:
- `CEP_SPECTATE=1` injects `--headed` (native Wayland or X11).
- `CEP_SPECTATE=1 CEP_VNC=1` injects `--headed --vnc` (Xtigervnc, required for
  vision tests on Wayland).

---

### 8. Footprint of the implementation

The feature touches 5 files. Container-side changes are irreducible; host-side changes
were minimized by removing the auto-launch of `vncviewer` (which was initially implemented
but then stripped to keep the code simple).

| File | Change | Why |
|------|--------|-----|
| `src/container/Dockerfile` | Add `tigervnc-standalone-server` | Provides `Xtigervnc` binary in the container |
| `src/container/image/run.py` | Start Xtigervnc on `:1` when headed + no display | Supplies the X11 display that Chromium renders to |
| `src/container/image/chrome-wrapper` | X11 branch: drop `--disable-gpu` and GPU compositing flags | Allows Chromium to paint to the X window (without these flags, the window content is black) |
| `src/check_cep` | `--vnc` flag, publish port 5900, print connect hint to stderr | Host side: expose the VNC port, tell the user how to connect |
| `tests/integration/conftest.py` | `CEP_VNC` env var → inject `--vnc` | Lets integration tests opt into VNC mode without changing test code |

The auto-launch of `vncviewer` (polling port 5900, spawning `subprocess.Popen`) was
implemented and tested, then removed. It saved one terminal but added ~56 lines of
polling code and a dependency on `vncviewer` being in `PATH`. The simpler approach — print
the connect command, let the user run it — is more robust and easier to understand.
