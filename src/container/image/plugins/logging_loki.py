"""logging_loki.py - Logging plugin: Grafana Loki.

Ships test result summary to Grafana Loki via HTTP push API.
Failure is non-fatal (warning only).
"""

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request

logger = logging.getLogger("logging_loki")


def _build_loki_labels(summary: dict) -> dict:
    """Build Loki stream labels from summary."""
    return {
        "job": "cep",
        "probe_location": summary.get("probe_location", "unknown"),
        "host_name": summary.get("hostname", "unknown"),
        "service_description": summary.get("servicedescription", "unknown"),
    }


def _build_payload(labels: dict, records: list, steps_data=None) -> dict:
    """Construct Loki push API payload."""
    values = []
    now_ns = str(int(time.time() * 1e9))

    if steps_data:
        # Ship the full steps.json content as a single log entry
        log_line = json.dumps(steps_data, ensure_ascii=False)
        values.append([now_ns, log_line])
    else:
        # Ship the summary as a single entry
        log_line = json.dumps(records, ensure_ascii=False)
        values.append([now_ns, log_line])

    return {"streams": [{"stream": labels, "values": values}]}


def _post_to_loki(push_url: str, payload_bytes: bytes,
                  loki_user: str, loki_password: str, loki_proxy: str) -> int:
    """POST JSON payload to Loki push API. Returns HTTP status code."""
    handlers = []

    # TLS: disable certificate verification
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    handlers.append(urllib.request.HTTPSHandler(context=ssl_ctx))

    # Proxy
    if loki_proxy:
        handlers.append(urllib.request.ProxyHandler({"https": loki_proxy, "http": loki_proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))

    # Basic auth
    if loki_user and loki_password:
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, push_url, loki_user, loki_password)
        handlers.append(urllib.request.HTTPBasicAuthHandler(password_mgr))

    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        push_url,
        data=payload_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    response = opener.open(req, timeout=10)
    return response.status


def ship_logs(test_name: str, summary: dict) -> None:
    """Ship test result summary to Grafana Loki.

    Args:
        test_name: TESTNAME — symbolic identifier
        summary: Dict with hostname, servicedescription, status, duration, etc.

    Environment variables:
        LOKI_ENDPOINT: Loki base URL
        LOKI_USER: Basic auth username (optional)
        LOKI_PASSWORD: Basic auth password (optional)
        LOKI_PROXY: HTTP proxy (optional)

    Raises:
        RuntimeError: On shipping failure (caught by run.py, non-fatal)
    """
    loki_endpoint = os.environ.get("LOKI_ENDPOINT")
    if not loki_endpoint:
        return

    loki_user = os.environ.get("LOKI_USER", "")
    loki_password = os.environ.get("LOKI_PASSWORD", "")
    loki_proxy = os.environ.get("LOKI_PROXY", "")

    push_url = loki_endpoint.rstrip("/") + "/loki/api/v1/push"
    labels = _build_loki_labels(summary)

    # Try to read steps.json for richer log content
    steps_data = None
    steps_path = os.path.join(os.path.expanduser("~"), "results", "steps.json")
    if os.path.exists(steps_path):
        try:
            with open(steps_path, "r") as f:
                content = f.read()
            if content.strip():
                steps_data = json.loads(content)
        except (json.JSONDecodeError, IOError) as e:
            logger.debug(f"Could not read steps.json: {e}")

    payload = _build_payload(labels, summary, steps_data)
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    try:
        status = _post_to_loki(push_url, payload_bytes, loki_user, loki_password, loki_proxy)
        logger.debug(f"Loki: HTTP {status} from {push_url}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"loki: HTTP {e.code} {e.reason} from {push_url}")
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "timed out" in reason.lower():
            raise RuntimeError(f"loki: timeout after 10s connecting to {push_url}")
        raise RuntimeError(f"loki: {reason} connecting to {push_url}")
    except Exception as e:
        raise RuntimeError(f"loki: {e} for {push_url}")
