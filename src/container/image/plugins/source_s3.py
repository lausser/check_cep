"""source_s3.py - Test source plugin: S3 download.

Downloads test archive from S3, unpacks into ~/tests.
Uses /testscripts-cache for local caching to avoid redundant downloads.
"""

import logging
import os
import tarfile

logger = logging.getLogger("source_s3")


def acquire_tests(test_name: str, dest_path: str) -> None:
    """Download test archive from S3 and unpack into dest_path.

    Args:
        test_name: TESTNAME — symbolic identifier, used as S3 object key component
        dest_path: Container-side path where tests must be placed ("~/tests")

    Environment variables used:
        S3_ENDPOINT: S3 API URL
        S3_BUCKET: Bucket containing test archives
        AWS_ACCESS_KEY_ID: S3 access key
        AWS_SECRET_ACCESS_KEY: S3 secret key

    Raises:
        RuntimeError: If download or extraction fails
    """
    import boto3

    s3_endpoint = os.environ.get("S3_ENDPOINT")
    s3_bucket = os.environ.get("S3_BUCKET")
    aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

    if not all([s3_endpoint, s3_bucket, aws_access_key_id, aws_secret_access_key]):
        raise RuntimeError("S3 credentials incomplete: need S3_ENDPOINT, S3_BUCKET, "
                          "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")

    client_args = {
        "aws_access_key_id": aws_access_key_id,
        "aws_secret_access_key": aws_secret_access_key,
        "endpoint_url": s3_endpoint,
    }
    s3 = boto3.client("s3", **client_args)

    # Build S3 key from test_name
    # test_name is "hostname__servicedescription" (URL-safe)
    file_key = f"{test_name}/scripts.tgz"

    cache_dir = "/home/pwuser/testscripts-cache"
    cached_tgz = os.path.join(cache_dir, test_name, "scripts.tgz")

    download = True

    # Check cache
    if os.path.exists(cached_tgz):
        try:
            local_modtime = os.path.getmtime(cached_tgz)
            local_size = os.path.getsize(cached_tgz)
            response = s3.head_object(Bucket=s3_bucket, Key=file_key)
            s3_modtime = response["LastModified"].timestamp()
            s3_size = response["ContentLength"]
            if local_modtime >= s3_modtime and local_size == s3_size:
                logger.debug(f"{file_key} is cached")
                download = False
            else:
                logger.debug(f"cached {file_key} is outdated")
        except Exception as e:
            logger.debug(f"Cache check failed: {e}, will download")

    if download:
        logger.debug(f"downloading {file_key} from bucket {s3_bucket}")
        try:
            # Ensure cache directory exists
            os.makedirs(os.path.dirname(cached_tgz), exist_ok=True)
            s3.download_file(s3_bucket, file_key, cached_tgz)
        except Exception as e:
            raise RuntimeError(f"Failed to download {file_key} from {s3_bucket}: {e}")

    # Extract to dest_path
    try:
        os.makedirs(dest_path, exist_ok=True)
        with tarfile.open(cached_tgz, mode="r:gz") as tar:
            tar.extractall(path=dest_path)
        logger.debug(f"Extracted {cached_tgz} to {dest_path}")
    except Exception as e:
        raise RuntimeError(f"Failed to extract {cached_tgz}: {e}")
