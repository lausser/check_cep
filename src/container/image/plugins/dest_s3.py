"""dest_s3.py - Result destination plugin: S3 upload.

Packages artefacts from ~/results, uploads to S3 with Nagios-state-based tags
for lifecycle management. Records S3 report URL in test-meta.json.
"""

import base64
import hashlib
import json
import logging
import os
import pathlib
import time
from urllib import parse

logger = logging.getLogger("dest_s3")


def _update_nagios_state(state_info, new_state):
    """Update Nagios service state for S3 tagging.

    Args:
        state_info: String formatted as "state/state_type/current_attempt/max_check_attempts/downtime/last_time_ok"
        new_state: Status string (OK, WARNING, CRITICAL, UNKNOWN)

    Returns:
        Tuple of (state, state_type, downtime, duration, transition, last_time_ok)
    """
    try:
        state, state_type, current_attempt, max_check_attempts, downtime, last_time_ok = state_info.split("/")
        current_attempt = int(current_attempt)
        max_check_attempts = int(max_check_attempts)
        downtime = int(downtime)
        try:
            last_time_ok = int(last_time_ok)
        except (ValueError, TypeError):
            last_time_ok = 0
    except ValueError:
        return new_state, "HARD", 0, 0, "unknown", 0

    if new_state == "OK":
        new_state_type = "HARD"
        new_current_attempt = 1
    else:
        if state == "OK":
            new_current_attempt = 1
            new_state_type = "SOFT"
            if new_current_attempt + 1 > max_check_attempts:
                new_state_type = "HARD"
        else:
            if state_type == "SOFT":
                if current_attempt + 1 >= max_check_attempts:
                    new_state_type = "HARD"
                    new_current_attempt = max_check_attempts
                else:
                    new_state_type = "SOFT"
                    new_current_attempt = current_attempt + 1
            else:
                new_state_type = "HARD"
                new_current_attempt = max_check_attempts

    if state == "OK" and new_state == "OK":
        transition = "okok"
        duration = 0
    elif state == "OK" and new_state != "OK":
        transition = "oknok"
        duration = int(time.time()) - last_time_ok
    else:
        transition = "noknok"
        duration = int(time.time()) - last_time_ok

    return new_state, new_state_type, downtime, duration, transition, last_time_ok


def _create_tags(state_tuple):
    """Create S3 object tags from Nagios state tuple."""
    state, state_type, downtime, duration, transition, last_time_ok = state_tuple
    duration_72h = 3600 * 72
    return {
        "hardstate": "true" if state_type == "HARD" else "false",
        "state": state.lower(),
        "downtime": "true" if downtime else "false",
        "longstate": "true" if duration > duration_72h else "false",
    }


def publish_results(test_name: str, results_path: str, nagios_state: int) -> None:
    """Package and upload artefacts from results_path to S3.

    Args:
        test_name: TESTNAME — symbolic identifier
        results_path: Container-side path containing raw Playwright output ("~/results")
        nagios_state: Playwright exit code (0=pass, 1=fail, 2=error)

    Environment variables used:
        S3_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
        S3_REPORT_BUCKET, REPORT_PATH, NAGIOS_HOSTNAME, NAGIOS_SERVICEDESC,
        PROBE_LOCATION, NAGIOS_CURRENT_STATUS

    Raises:
        RuntimeError: On upload failure
    """
    import boto3

    s3_endpoint = os.environ.get("S3_ENDPOINT")
    aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    s3_report_bucket = os.environ.get("S3_REPORT_BUCKET")
    report_path = os.environ.get("REPORT_PATH")
    hostname = os.environ.get("NAGIOS_HOSTNAME", "")
    servicedescription = os.environ.get("NAGIOS_SERVICEDESC", "")
    probe_location = os.environ.get("PROBE_LOCATION", "unknown")
    current_status = os.environ.get("NAGIOS_CURRENT_STATUS")

    if not all([s3_endpoint, aws_access_key_id, aws_secret_access_key, s3_report_bucket]):
        raise RuntimeError("S3 report credentials incomplete")

    s3 = boto3.client("s3",
                      aws_access_key_id=aws_access_key_id,
                      aws_secret_access_key=aws_secret_access_key,
                      endpoint_url=s3_endpoint)

    status_str = {0: "OK", 1: "WARNING", 2: "CRITICAL"}.get(nagios_state, "UNKNOWN")
    now = str(int(time.time()))

    # Build S3 folder path
    if report_path:
        s3_folder = report_path
        s3_folder = s3_folder.replace("%h", hostname)
        s3_folder = s3_folder.replace("%s", servicedescription)
        s3_folder = s3_folder.replace("%l", probe_location)
        s3_folder = s3_folder.replace("%t", now)
    elif hostname:
        s3_folder = f"{servicedescription}/{now}"
    else:
        s3_folder = now

    # Update test-meta.json with report URL
    meta_path = os.path.join(results_path, "test-meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            meta = json.load(f)
    meta["report_url"] = f"/{s3_report_bucket}/{s3_folder}/index.html"
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)

    # Build S3 tags
    tags = ""
    if current_status:
        try:
            next_state = _update_nagios_state(current_status, status_str)
            tag_dict = _create_tags(next_state)
            tags = parse.urlencode(tag_dict)
        except Exception as e:
            logger.warning(f"Could not compute S3 tags: {e}")

    # Upload all files
    upload_errors = []
    for path in pathlib.Path(results_path).rglob("*"):
        if path.is_file():
            relative = path.relative_to(results_path).as_posix()
            s3_key = f"{s3_folder}/{relative}"
            try:
                with open(path, "rb") as f:
                    content = f.read()
                    md5_hash = hashlib.md5(content).digest()
                    md5_b64 = base64.b64encode(md5_hash).decode("utf-8")
                kwargs = {
                    "Bucket": s3_report_bucket,
                    "Key": s3_key,
                    "Body": content,
                    "ContentMD5": md5_b64,
                }
                if tags:
                    kwargs["Tagging"] = tags
                s3.put_object(**kwargs)
                logger.debug(f"Uploaded {path} to {s3_report_bucket}/{s3_key}")
            except Exception as e:
                upload_errors.append(f"upload failed for {s3_key}: {e}")

    if upload_errors:
        raise RuntimeError("____".join(upload_errors))
