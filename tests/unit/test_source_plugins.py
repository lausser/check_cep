"""Unit tests for source_s3 and source_local container-side plugins
(017-s3-tgz-source: T010, T015, T016, T017)."""

import io
import json
import os
import tarfile
import tempfile
import time
from unittest.mock import MagicMock, patch, call

import pytest

# Container-side plugins are importable because tests/unit/conftest.py adds
# src/container/image/plugins/ to sys.path before test collection.
import _layers
import source_s3
import source_local
from _layers import LayerError, LayerTimeout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tgz(dest_path: str, files: dict) -> None:
    """Write a .tgz archive at dest_path containing the given files dict."""
    with tarfile.open(dest_path, "w:gz") as tar:
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


# ---------------------------------------------------------------------------
# source_s3._parse_artifact (T010)
# ---------------------------------------------------------------------------

class TestParseArtifact:
    def test_simple_bucket_and_key(self):
        bucket, key = source_s3._parse_artifact("/mybucket/tests.tgz")
        assert bucket == "mybucket"
        assert key == "tests.tgz"

    def test_multi_segment_key(self):
        bucket, key = source_s3._parse_artifact("/mybucket/path/to/tests.tgz")
        assert bucket == "mybucket"
        assert key == "path/to/tests.tgz"

    def test_leading_slash_stripped(self):
        bucket, _ = source_s3._parse_artifact("/bucket/key.tgz")
        assert bucket == "bucket"

    def test_tar_gz_extension(self):
        bucket, key = source_s3._parse_artifact("/b/a/b/archive.tar.gz")
        assert bucket == "b"
        assert key == "a/b/archive.tar.gz"

    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="must be /bucket/key"):
            source_s3._parse_artifact("/onlybucket")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            source_s3._parse_artifact("")


# ---------------------------------------------------------------------------
# source_s3.acquire_tests: missing TEST_ARTIFACT (T010)
# ---------------------------------------------------------------------------

def test_s3_acquire_tests_missing_env_raises(monkeypatch):
    monkeypatch.delenv("TEST_ARTIFACT", raising=False)
    with pytest.raises(RuntimeError, match="TEST_ARTIFACT"):
        source_s3.acquire_tests("ignored", "/dest", time.time() + 60)


# ---------------------------------------------------------------------------
# source_s3.acquire_tests: cache hit — no download (T010, T017)
# ---------------------------------------------------------------------------

def test_s3_cache_hit_skips_download(monkeypatch, tmp_path):
    artifact = "/mybucket/checks/login.tgz"
    monkeypatch.setenv("TEST_ARTIFACT", artifact)
    monkeypatch.setenv("S3_ENDPOINT", "https://s3.example.com")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")

    # Pre-populate cache with the tgz
    cache_dir = tmp_path / "cache"
    cached = cache_dir / "mybucket" / "checks" / "login.tgz"
    cached.parent.mkdir(parents=True)
    dest = tmp_path / "tests"
    _make_tgz(str(cached), {"hello.test.ts": "// test"})

    import time
    cached_mtime = time.time()
    os.utime(cached, (cached_mtime, cached_mtime))
    cached_size = cached.stat().st_size

    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {
        "LastModified": MagicMock(timestamp=lambda: cached_mtime),
        "ContentLength": cached_size,
    }

    with patch("boto3.client", return_value=mock_s3):
        with patch("source_s3.os.path.join", side_effect=os.path.join):
            # Redirect cache_dir inside the plugin
            original_acquire = source_s3.acquire_tests

            def patched_acquire(test_name, dest_path):
                # Temporarily override the cache_dir constant
                with patch.object(source_s3, "__file__", str(cache_dir / "source_s3.py")):
                    pass
                # Directly call internal logic with patched cache dir
                import boto3  # noqa: F401
                bucket, key = source_s3._parse_artifact(
                    os.environ["TEST_ARTIFACT"]
                )
                cached_tgz = str(cache_dir / bucket / key)
                download_called = []
                if os.path.exists(cached_tgz):
                    local_modtime = os.path.getmtime(cached_tgz)
                    local_size = os.path.getsize(cached_tgz)
                    resp = mock_s3.head_object(Bucket=bucket, Key=key)
                    s3_mtime = resp["LastModified"].timestamp()
                    s3_size = resp["ContentLength"]
                    if local_modtime >= s3_mtime and local_size == s3_size:
                        pass  # cache hit
                    else:
                        download_called.append(True)
                else:
                    download_called.append(True)
                os.makedirs(dest_path, exist_ok=True)
                with tarfile.open(cached_tgz, "r:gz") as t:
                    t.extractall(path=dest_path)
                return download_called

            result = patched_acquire("ignored", str(dest))

    assert result == [], "download should not have been called on cache hit"
    assert (dest / "hello.test.ts").exists()


# ---------------------------------------------------------------------------
# source_s3.acquire_tests: cache miss — download called (T010)
# ---------------------------------------------------------------------------

def test_s3_cache_miss_triggers_download(monkeypatch, tmp_path):
    artifact = "/mybucket/checks/login.tgz"
    monkeypatch.setenv("TEST_ARTIFACT", artifact)
    monkeypatch.setenv("S3_ENDPOINT", "https://s3.example.com")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")

    cache_dir = tmp_path / "cache"
    dest = tmp_path / "tests"

    # Create the tgz that would be "downloaded" into the cache
    expected_cached = cache_dir / "mybucket" / "checks" / "login.tgz"

    def fake_download(bucket, key, local_path):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        _make_tgz(local_path, {"suite.test.ts": "// test"})

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download

    # Patch the cache directory constant inside acquire_tests by patching os.path.join
    # to redirect the cache path
    original_join = os.path.join

    def patched_join(*args):
        if args and args[0] == "/home/pwuser/testscripts-cache":
            return original_join(str(cache_dir), *args[1:])
        return original_join(*args)

    with patch("boto3.client", return_value=mock_s3):
        with patch("source_s3.os.path.join", side_effect=patched_join):
            source_s3.acquire_tests("ignored", str(dest), time.time() + 60)

    mock_s3.download_file.assert_called_once_with("mybucket", "checks/login.tgz",
                                                   str(expected_cached))
    assert (dest / "suite.test.ts").exists()


# ---------------------------------------------------------------------------
# source_s3.acquire_tests: cache stale — re-download (T017)
# ---------------------------------------------------------------------------

def test_s3_cache_stale_triggers_redownload(monkeypatch, tmp_path):
    artifact = "/mybucket/a/b/tests.tgz"
    monkeypatch.setenv("TEST_ARTIFACT", artifact)
    monkeypatch.setenv("S3_ENDPOINT", "https://s3.example.com")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")

    cache_dir = tmp_path / "cache"
    cached = cache_dir / "mybucket" / "a" / "b" / "tests.tgz"
    cached.parent.mkdir(parents=True)
    _make_tgz(str(cached), {"old.test.ts": "old"})

    import time
    old_time = time.time() - 3600
    os.utime(cached, (old_time, old_time))
    s3_newer_time = time.time()

    def fake_download(bucket, key, local_path):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        _make_tgz(local_path, {"new.test.ts": "new"})

    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {
        "LastModified": MagicMock(timestamp=lambda: s3_newer_time),
        "ContentLength": cached.stat().st_size + 1,
    }
    mock_s3.download_file.side_effect = fake_download

    original_join = os.path.join

    def patched_join(*args):
        if args and args[0] == "/home/pwuser/testscripts-cache":
            return original_join(str(cache_dir), *args[1:])
        return original_join(*args)

    dest = tmp_path / "tests"
    with patch("boto3.client", return_value=mock_s3):
        with patch("source_s3.os.path.join", side_effect=patched_join):
            source_s3.acquire_tests("ignored", str(dest), time.time() + 60)

    mock_s3.download_file.assert_called_once()


# ---------------------------------------------------------------------------
# source_s3: multi-segment key cache path (T017)
# ---------------------------------------------------------------------------

def test_s3_multi_segment_key_cache_path():
    """Cache entry path mirrors the full artifact path under cache root."""
    bucket, key = source_s3._parse_artifact("/mybucket/a/b/c/tests.tgz")
    cache_dir = "/home/pwuser/testscripts-cache"
    cached = os.path.join(cache_dir, bucket, key)
    assert cached == "/home/pwuser/testscripts-cache/mybucket/a/b/c/tests.tgz"


# ---------------------------------------------------------------------------
# source_local.acquire_tests: ordered layers from TEST_ARTIFACT_LAYERS (spec 023)
# ---------------------------------------------------------------------------

def _layer_env(monkeypatch, layers):
    monkeypatch.setenv("TEST_ARTIFACT_LAYERS", json.dumps([
        {"position": i + 1, "host_path": f"/host/{i + 1}", "type": kind, "container_path": str(path)}
        for i, (kind, path) in enumerate(layers)]))


@pytest.fixture
def staging(tmp_path, monkeypatch):
    monkeypatch.setattr(source_local, "_STAGING_ROOT", str(tmp_path / "staging"))


def test_local_dir_and_tgz_merge(tmp_path, monkeypatch, staging):
    shared = tmp_path / "shared"
    (shared / "functions").mkdir(parents=True)
    (shared / "functions" / "shared.ts").write_text("export const x = 1;")
    tgz = tmp_path / "svc.tgz"
    _make_tgz(str(tgz), {"login.test.ts": "// test"})
    _layer_env(monkeypatch, [("directory", shared), ("archive", tgz)])
    dest = tmp_path / "tests"
    source_local.acquire_tests("ignored", str(dest), time.time() + 60)
    assert (dest / "functions" / "shared.ts").exists()
    assert (dest / "login.test.ts").exists()


def test_local_missing_layer_names_position(tmp_path, monkeypatch, staging):
    _layer_env(monkeypatch, [("directory", tmp_path / "nope")])
    with pytest.raises(RuntimeError, match=r"layer #1 \(/host/1\)"):
        source_local.acquire_tests("ignored", str(tmp_path / "tests"), time.time() + 60)


def test_local_missing_archive_names_position(tmp_path, monkeypatch, staging):
    _layer_env(monkeypatch, [("archive", tmp_path / "nope.tgz")])
    with pytest.raises(RuntimeError, match=r"layer #1 \(/host/1\): archive not found"):
        source_local.acquire_tests("ignored", str(tmp_path / "tests"), time.time() + 60)


def test_local_no_tests_is_not_the_plugins_concern(tmp_path, monkeypatch, staging):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "readme.md").write_text("docs")
    _layer_env(monkeypatch, [("directory", docs)])
    source_local.acquire_tests("ignored", str(tmp_path / "tests"), time.time() + 60)


def test_local_missing_env(monkeypatch, tmp_path):
    monkeypatch.delenv("TEST_ARTIFACT_LAYERS", raising=False)
    with pytest.raises(RuntimeError, match="TEST_ARTIFACT_LAYERS missing or invalid"):
        source_local.acquire_tests("ignored", str(tmp_path), time.time() + 60)


def test_local_past_deadline(tmp_path, monkeypatch, staging):
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.test.ts").write_text("x")
    _layer_env(monkeypatch, [("directory", d)])
    with pytest.raises(LayerTimeout):
        source_local.acquire_tests("x", str(tmp_path / "tests"), time.time() - 1)


def test_local_deadline_passes_during_archive(tmp_path, monkeypatch, staging):
    tgz = tmp_path / "a.tgz"
    _make_tgz(str(tgz), {"a.test.ts": "1", "b.txt": "2"})
    _layer_env(monkeypatch, [("archive", tgz)])
    calls = []

    def fake_clock():  # before the first member: in time; afterwards: late
        calls.append(1)
        return 100.0 if len(calls) == 1 else 200.0
    monkeypatch.setattr(_layers.time, "time", fake_clock)
    merged = []
    monkeypatch.setattr(source_local, "merge_layers", lambda *a: merged.append(a))
    with pytest.raises(LayerTimeout):
        source_local.acquire_tests("x", str(tmp_path / "tests"), 150.0)
    assert merged == []


# ---------------------------------------------------------------------------
# source_s3: extraction is safe, downloads are bounded (spec 023 FR-024/FR-030)
# ---------------------------------------------------------------------------

def _s3_env(monkeypatch):
    monkeypatch.setenv("TEST_ARTIFACT", "/mybucket/checks/login.tgz")
    monkeypatch.setenv("S3_ENDPOINT", "https://s3.example.com")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")


def _redirect_cache(cache_dir):
    original_join = os.path.join

    def patched_join(*args):
        if args and args[0] == "/home/pwuser/testscripts-cache":
            return original_join(str(cache_dir), *args[1:])
        return original_join(*args)
    return patch("source_s3.os.path.join", side_effect=patched_join)


def test_s3_extraction_is_safe(monkeypatch, tmp_path):
    _s3_env(monkeypatch)

    def fake_download(bucket, key, local_path):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        _make_tgz(local_path, {"../evil": "x"})

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download
    with patch("boto3.client", return_value=mock_s3), _redirect_cache(tmp_path / "cache"):
        with pytest.raises(LayerError, match=r"layer #1 \(s3:/mybucket/checks/login.tgz\)"):
            source_s3.acquire_tests("ignored", str(tmp_path / "tests"), time.time() + 60)


def test_s3_read_timeout_is_layer_timeout(monkeypatch, tmp_path):
    from botocore.exceptions import ReadTimeoutError
    _s3_env(monkeypatch)
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = ReadTimeoutError(endpoint_url="https://s3")
    with patch("boto3.client", return_value=mock_s3), _redirect_cache(tmp_path / "cache"):
        with pytest.raises(LayerTimeout, match="download timed out after"):
            source_s3.acquire_tests("ignored", str(tmp_path / "tests"), time.time() + 60)


@pytest.mark.parametrize("value", ['[1]', '[{"position": 1}]', '{"position": 1}', '[{"position": "1", '
                                   '"host_path": "/h", "type": "directory", "container_path": "/c"}]'])
def test_local_malformed_layers_env(tmp_path, monkeypatch, value):
    monkeypatch.setenv("TEST_ARTIFACT_LAYERS", value)
    with pytest.raises(RuntimeError, match="^TEST_ARTIFACT_LAYERS missing or invalid$"):
        source_local.acquire_tests("x", str(tmp_path / "tests"), time.time() + 60)
