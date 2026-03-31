"""source_s3.py - Test source plugin: S3 download.

Downloads a .tgz test archive from S3 using the explicit artifact path given
in TEST_ARTIFACT (format: /bucket/path/to/testfolder.tgz).  Caches the
downloaded archive under testscripts-cache/ mirroring the artifact path to
avoid redundant downloads.  Unpacks into ~/tests.
"""

import logging
import os
import tarfile

logger = logging.getLogger("source_s3")


def _parse_artifact(test_artifact: str) -> tuple:
    """Parse TEST_ARTIFACT into (bucket, key).

    Args:
        test_artifact: Path of the form /bucket/path/to/archive.tgz

    Returns:
        (bucket, key) tuple

    Raises:
        ValueError: If the artifact path cannot be parsed into bucket + key
    """
    stripped = test_artifact.lstrip("/")
    if "/" not in stripped:
        raise ValueError(
            f"TEST_ARTIFACT must be /bucket/key/archive.tgz, got: {test_artifact!r}"
        )
    bucket, key = stripped.split("/", 1)
    return bucket, key


def acquire_tests(_test_name: str, dest_path: str) -> None:
    """Download test archive from S3 and unpack into dest_path.

    Args:
        _test_name: Unused — artifact path is taken from TEST_ARTIFACT env var
        dest_path: Container-side path where tests must be placed (/home/pwuser/tests)

    Environment variables used:
        TEST_ARTIFACT: Artifact path /bucket/key/archive.{tgz,tar.gz}
        S3_ENDPOINT:   S3 API URL
        AWS_ACCESS_KEY_ID:     S3 access key
        AWS_SECRET_ACCESS_KEY: S3 secret key

    Raises:
        RuntimeError: If download or extraction fails
    """
    import boto3

    test_artifact = os.environ.get("TEST_ARTIFACT")
    if not test_artifact:
        raise RuntimeError(
            "TEST_ARTIFACT environment variable is not set; "
            "pass --test-artifact=/bucket/path/archive.tgz to check_cep"
        )

    s3_endpoint = os.environ.get("S3_ENDPOINT")
    aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

    if not all([s3_endpoint, aws_access_key_id, aws_secret_access_key]):
        raise RuntimeError(
            "S3 credentials incomplete: need S3_ENDPOINT, "
            "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
        )

    try:
        bucket, key = _parse_artifact(test_artifact)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=s3_endpoint,
    )

    cache_dir = "/home/pwuser/testscripts-cache"
    cached_tgz = os.path.join(cache_dir, bucket, key)

    download = True

    if os.path.exists(cached_tgz):
        try:
            local_modtime = os.path.getmtime(cached_tgz)
            local_size = os.path.getsize(cached_tgz)
            response = s3.head_object(Bucket=bucket, Key=key)
            s3_modtime = response["LastModified"].timestamp()
            s3_size = response["ContentLength"]
            if local_modtime >= s3_modtime and local_size == s3_size:
                logger.debug("cache hit: %s", test_artifact)
                download = False
            else:
                logger.debug("cache stale: %s", test_artifact)
        except Exception as exc:
            logger.debug("cache check failed: %s, will download", exc)

    if download:
        logger.debug("downloading s3://%s/%s", bucket, key)
        try:
            os.makedirs(os.path.dirname(cached_tgz), exist_ok=True)
            s3.download_file(bucket, key, cached_tgz)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to download s3://{bucket}/{key}: {exc}"
            ) from exc

    try:
        os.makedirs(dest_path, exist_ok=True)
        with tarfile.open(cached_tgz, mode="r:gz") as tar:
            tar.extractall(path=dest_path)
        logger.debug("extracted %s to %s", cached_tgz, dest_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to extract {cached_tgz}: {exc}") from exc
