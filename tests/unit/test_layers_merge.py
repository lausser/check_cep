"""Unit tests for the container-side layer merge helper plugins/_layers.py
(spec 023 US2: FR-021…FR-026, data-model §3)."""
import io
import os
import tarfile
import time

import pytest

import _layers
from _layers import LayerError, LayerTimeout, OverrideRecord


def _write(root, rel, content="x"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _roots(*dirs):
    return [(i + 1, str(d), f"layer #{i + 1} ({d})") for i, d in enumerate(dirs)]


def _listing(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


@pytest.fixture
def layers(tmp_path):
    a, b, dest = tmp_path / "a", tmp_path / "b", tmp_path / "dest"
    a.mkdir()
    b.mkdir()
    return a, b, dest


# ---------------------------------------------------------------------------
# (a)/(b) merge semantics and override records
# ---------------------------------------------------------------------------

def test_two_dirs_merge(layers):
    a, b, dest = layers
    _write(a, "functions/shared.ts", "a")
    _write(a, "same.txt", "from a")
    _write(a, ".npmrc", "rc")
    _write(a, "playwright/.auth/x.json", "{}")
    _write(b, "functions/extra.ts", "b")
    _write(b, "same.txt", "from b")
    _layers.merge_layers(_roots(a, b), str(dest), time.time() + 60)
    assert (dest / "functions/shared.ts").read_text() == "a"
    assert (dest / "functions/extra.ts").read_text() == "b"
    assert (dest / "same.txt").read_text() == "from b"
    assert (dest / ".npmrc").exists()
    assert (dest / "playwright/.auth/x.json").exists()


def test_override_records(layers):
    a, b, dest = layers
    _write(a, "playwright.config.ts", "1")
    _write(b, "playwright.config.ts", "2")
    overrides = _layers.merge_layers(_roots(a, b), str(dest), time.time() + 60)
    assert overrides == [OverrideRecord("playwright.config.ts", 2, 1)]


# ---------------------------------------------------------------------------
# (c)-(e) validation before any copy
# ---------------------------------------------------------------------------

def test_type_conflict(layers):
    a, b, dest = layers
    _write(a, "functions", "file")
    _write(a, "early.txt")
    _write(b, "functions/x.ts")
    with pytest.raises(LayerError) as exc:
        _layers.merge_layers(_roots(a, b), str(dest), time.time() + 60)
    msg = str(exc.value)
    assert "type conflict at functions" in msg
    assert "#1" in msg and "#2" in msg
    assert not dest.exists() or _listing(dest) == []


def test_escaping_symlinks_rejected(layers):
    a, _, dest = layers
    os.symlink("../../etc/passwd", a / "a")
    with pytest.raises(LayerError, match=r"layer #1"):
        _layers.merge_layers(_roots(a), str(dest), time.time() + 60)


def test_absolute_symlink_rejected(layers):
    a, _, dest = layers
    os.symlink("/etc/passwd", a / "abs")
    with pytest.raises(LayerError, match=r"layer #1"):
        _layers.merge_layers(_roots(a), str(dest), time.time() + 60)


def test_relative_in_tree_symlink_preserved(layers):
    a, _, dest = layers
    _write(a, "sub/file", "data")
    os.symlink("sub/file", a / "b")
    _layers.merge_layers(_roots(a), str(dest), time.time() + 60)
    assert os.readlink(dest / "b") == "sub/file"
    assert (dest / "b").read_text() == "data"


def test_fifo_rejected(layers):
    a, _, dest = layers
    os.mkfifo(a / "pipe")
    with pytest.raises(LayerError, match=r"layer #1"):
        _layers.merge_layers(_roots(a), str(dest), time.time() + 60)


# ---------------------------------------------------------------------------
# (f)/(h2) safe_extract
# ---------------------------------------------------------------------------

def _tgz(path, members):
    """members: list of (TarInfo, bytes-or-None)."""
    with tarfile.open(path, "w:gz") as tar:
        for info, data in members:
            if data is not None:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            else:
                tar.addfile(info)
    return str(path)


def _file(name, data=b"x"):
    return tarfile.TarInfo(name), data


def _special(name, kind, linkname=""):
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = linkname
    return info, None


@pytest.mark.parametrize("member", [
    _file("../evil"),
    _file("/abs"),
    _special("link", tarfile.SYMTYPE, "/etc"),
    _special("hard", tarfile.LNKTYPE, "../x"),
    _special("dev", tarfile.CHRTYPE),
], ids=["dotdot", "absolute", "symlink-out", "hardlink-out", "chardev"])
def test_safe_extract_rejects_unsafe_members(tmp_path, member):
    archive = _tgz(tmp_path / "bad.tgz", [_file("ok.txt"), member])
    with pytest.raises(LayerError, match=r"layer #3 \(/x/bad.tgz\)"):
        _layers.safe_extract(archive, str(tmp_path / "out"), "layer #3 (/x/bad.tgz)")


def test_safe_extract_corrupt_archive(tmp_path):
    archive = tmp_path / "junk.tgz"
    archive.write_bytes(os.urandom(512))
    with pytest.raises(LayerError, match="layer #1"):
        _layers.safe_extract(str(archive), str(tmp_path / "out"), "layer #1 (junk)")


def test_safe_extract_readonly_dir_member(tmp_path):
    ro = tarfile.TarInfo("ro")
    ro.type = tarfile.DIRTYPE
    ro.mode = 0o555
    archive = _tgz(tmp_path / "ro.tgz", [(ro, None), _file("ro/inside.txt", b"in")])
    out = tmp_path / "out"
    _layers.safe_extract(archive, str(out), "layer #1 (ro)")
    assert (out / "ro/inside.txt").read_text() == "in"
    os.chmod(out / "ro", 0o755)  # let pytest clean up


def test_safe_extract_past_deadline(tmp_path):
    archive = _tgz(tmp_path / "a.tgz", [_file("a.txt")])
    with pytest.raises(LayerTimeout):
        _layers.safe_extract(archive, str(tmp_path / "out"), "l", deadline=time.time() - 1)


def test_safe_extract_past_deadline_directories_only(tmp_path):
    d = tarfile.TarInfo("only")
    d.type = tarfile.DIRTYPE
    archive = _tgz(tmp_path / "d.tgz", [(d, None)])
    with pytest.raises(LayerTimeout):
        _layers.safe_extract(archive, str(tmp_path / "out"), "l", deadline=time.time() - 1)


# ---------------------------------------------------------------------------
# (g)-(i)
# ---------------------------------------------------------------------------

def test_same_layer_twice_is_harmless(layers, tmp_path):
    a, _, dest = layers
    _write(a, "x/y.txt", "v")
    _layers.merge_layers(_roots(a, a), str(dest), time.time() + 60)
    assert _listing(dest) == ["x", "x/y.txt"]
    assert (dest / "x/y.txt").read_text() == "v"


def test_copy_past_deadline(layers):
    a, _, dest = layers
    _write(a, "x.txt")
    with pytest.raises(LayerTimeout):
        _layers.merge_layers(_roots(a), str(dest), time.time() - 1)


def test_sources_unchanged(layers):
    a, b, dest = layers
    _write(a, "x.txt", "a")
    _write(b, "x.txt", "b")
    before = [(_listing(d), os.stat(d).st_mtime) for d in (a, b)]
    _layers.merge_layers(_roots(a, b), str(dest), time.time() + 60)
    (dest / "x.txt").write_text("changed by test")
    assert [(_listing(d), os.stat(d).st_mtime) for d in (a, b)] == before
    assert (b / "x.txt").read_text() == "b"


def test_plan_past_deadline(layers):
    """Validation walks every layer, so it must respect the deadline too (FR-030)."""
    a, _, dest = layers
    _write(a, "x.txt")
    with pytest.raises(LayerTimeout):
        _layers.plan_merge(_roots(a), deadline=time.time() - 1)
    assert not dest.exists()
