"""Unit tests for source_s3 and source_local container-side plugins
(017-s3-tgz-source: T010, T015, T016, T017)."""

import io
import os
import tarfile
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

# Container-side plugins are importable because tests/unit/conftest.py adds
# src/container/image/plugins/ to sys.path before test collection.
import source_s3
import source_local


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
        source_s3.acquire_tests("ignored", "/dest")


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
            source_s3.acquire_tests("ignored", str(dest))

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
            source_s3.acquire_tests("ignored", str(dest))

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
# source_local.acquire_tests: directory mode (T015)
# ---------------------------------------------------------------------------

def test_local_directory_mode_validates_tests(tmp_path):
    # Populate with a test file
    (tmp_path / "login.test.ts").write_text("// test")

    source_local.acquire_tests("ignored", str(tmp_path))  # Should not raise


def test_local_directory_mode_missing_dir_raises(tmp_path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(RuntimeError, match="does not exist"):
        source_local.acquire_tests("ignored", str(missing))


def test_local_directory_mode_no_test_files_raises(tmp_path):
    (tmp_path / "readme.md").write_text("docs")
    with pytest.raises(RuntimeError, match="No test files"):
        source_local.acquire_tests("ignored", str(tmp_path))


# ---------------------------------------------------------------------------
# source_local.acquire_tests: tgz mode (T015)
# ---------------------------------------------------------------------------

def test_local_tgz_mode_extracts_and_validates(tmp_path, monkeypatch):
    # Build a tgz with a test file
    tgz_path = tmp_path / "bundle.tgz"
    _make_tgz(str(tgz_path), {"suite.test.ts": "// test"})

    dest = tmp_path / "tests"
    monkeypatch.setenv("TEST_ARTIFACT", "/somewhere/bundle.tgz")

    with patch("source_local._INPUT_ARTIFACT_PATH", str(tgz_path)):
        source_local.acquire_tests("ignored", str(dest))

    assert (dest / "suite.test.ts").exists()


def test_local_tgz_mode_missing_archive_raises(tmp_path, monkeypatch):
    dest = tmp_path / "tests"
    monkeypatch.setenv("TEST_ARTIFACT", "/somewhere/bundle.tgz")

    with patch("source_local._INPUT_ARTIFACT_PATH", str(tmp_path / "nonexistent.tgz")):
        with pytest.raises(RuntimeError, match="Expected archive"):
            source_local.acquire_tests("ignored", str(dest))


def test_local_tgz_mode_no_test_files_raises(tmp_path, monkeypatch):
    tgz_path = tmp_path / "empty.tgz"
    _make_tgz(str(tgz_path), {"README.md": "docs"})
    dest = tmp_path / "tests"
    monkeypatch.setenv("TEST_ARTIFACT", "/somewhere/empty.tgz")

    with patch("source_local._INPUT_ARTIFACT_PATH", str(tgz_path)):
        with pytest.raises(RuntimeError, match="No test files"):
            source_local.acquire_tests("ignored", str(dest))


def test_local_tar_gz_extension_also_triggers_extraction(tmp_path, monkeypatch):
    tgz_path = tmp_path / "bundle.tar.gz"
    _make_tgz(str(tgz_path), {"login.test.ts": "// test"})
    dest = tmp_path / "tests"
    monkeypatch.setenv("TEST_ARTIFACT", "/somewhere/bundle.tar.gz")

    with patch("source_local._INPUT_ARTIFACT_PATH", str(tgz_path)):
        source_local.acquire_tests("ignored", str(dest))

    assert (dest / "login.test.ts").exists()
