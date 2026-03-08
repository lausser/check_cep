# Lessons Learned

## X11 Forwarding into Rootless Podman Containers

**Context**: Implementing `--headed` mode so Playwright runs with a visible browser on the host desktop.

### 1. `--userns=keep-id` needs explicit UID mapping

The default `--userns=keep-id` maps the host user to the **same** UID inside the container (typically 1000). But the container's `pwuser` is UID 1001. Without `--userns=keep-id:uid=1001,gid=1001`, the process runs as the wrong user and can't find node_modules, tests, or the home directory structure it expects.

**Detection**: `podman run --userns=keep-id <image> id` shows `uid=1000(ubuntu)` instead of `uid=1001(pwuser)`.

**Fix**: Always specify `--userns=keep-id:uid=1001,gid=1001` to match the container user.

### 2. X11 socket must NOT use `:z` SELinux relabeling

Volume mounts normally use `:z` for SELinux. But `/tmp/.X11-unix` is a shared host socket — relabeling it with `:z` changes its SELinux context and breaks X11 for every other application on the host desktop.

**Prevention rule**: Never use `:z` on shared host resources (sockets, device files). Use `--security-opt label=disable` instead for the entire container.

### 3. Chrome requires `--ipc=host` for X11

Chrome uses the MIT-SHM (shared memory) X11 extension for rendering. Without `--ipc=host`, Chrome crashes or hangs on startup with cryptic errors about shared memory segments.

**Detection**: Browser launch fails with no useful error message; adding `--ipc=host` resolves it.

### 4. XWayland provides X11 on Wayland desktops automatically

KDE Plasma (and GNOME) on Wayland run XWayland by default, which provides `DISPLAY=:0` (or `:1`). No special Wayland configuration is needed — X11 forwarding "just works" because Chrome/Chromium uses X11 internally even on Wayland hosts.

### 5. `xhost +local:` is sufficient for container X11 access

No need for SSH-style X11 forwarding, `XAUTHORITY` sharing hacks, or complex `xauth` cookie manipulation. Since the container's network namespace shares the host's local Unix sockets via the bind mount, `xhost +local:` permits access. The Xauthority file is mounted as a fallback for setups that don't rely on `xhost`.

### 6. Headed mode changes the container's user namespace

`--userns=keep-id:uid=1001,gid=1001` changes how UIDs map between host and container. This means the `chown root:root` trick in `dest_local.py` (which normally maps container root to host user) works differently. Files written by pwuser in headed mode are already owned by the host user (since pwuser IS the host user via keep-id). This is fine — the ownership fixup in dest_local.py is harmless/idempotent either way.
