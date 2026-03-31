"""Unit-test fixtures and shared helpers.

Single source of truth for:
  - Loading the check_cep plugin module (not a proper package, requires importlib)
  - Loading container-side plugins (via sys.path into src/container/image/plugins/)
  - make_config() / make_ctx() test factories shared by multiple unit test modules
"""
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Load check_cep (host-side plugin — single file, not a package)
# ---------------------------------------------------------------------------

_PLUGIN = Path(__file__).parent.parent.parent / "src" / "check_cep"
_loader = importlib.machinery.SourceFileLoader("check_cep_mod", str(_PLUGIN))
_spec = importlib.util.spec_from_file_location("check_cep_mod", str(_PLUGIN), loader=_loader)
_cep_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cep_mod)
# Register so unittest.mock.patch can resolve "check_cep_mod.*"
sys.modules.setdefault("check_cep_mod", _cep_mod)

# Re-export the symbols used across unit test modules
RunConfig = _cep_mod.RunConfig
RunContext = _cep_mod.RunContext
derive_testname = _cep_mod.derive_testname
derive_testident = _cep_mod.derive_testident
sanitize_container_name = _cep_mod.sanitize_container_name
resolve_path_template = _cep_mod.resolve_path_template
build_env_vars = _cep_mod.build_env_vars
build_podman_command = _cep_mod.build_podman_command
resolve_report_url = _cep_mod.resolve_report_url
LocalCleanup = _cep_mod.LocalCleanup
CleanupResult = _cep_mod.CleanupResult
parse_retention = _cep_mod.parse_retention
run_cleanup = _cep_mod.run_cleanup

# ---------------------------------------------------------------------------
# Container-side plugin imports (needed by test_source_plugins.py)
# ---------------------------------------------------------------------------

_PLUGINS_DIR = Path(__file__).parent.parent.parent / "src" / "container" / "image" / "plugins"
if str(_PLUGINS_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGINS_DIR))

# ---------------------------------------------------------------------------
# Test factories — shared by test_run_context.py and test_cleanup.py
# ---------------------------------------------------------------------------

def make_config(**overrides) -> RunConfig:
    """Build a RunConfig with sensible test defaults. Override any field by name."""
    defaults = dict(
        host_name="testhost",
        service_description="TestService",
        image="ghcr.io/example/playwright:latest",
        probe_location="local",
        test_source="local",
        result_dest="local",
        logging="none",
        test_dir=None,
        test_artifact=None,
        result_dir="/omd/var/tmp/check_cep/%h/%s/%t",
        testscripts_cache="/omd/var/tmp/check_cep_cache",
        report_retention=None,
        timeout=60,
        memory_limit="2g",
        debug=False,
        shell=False,
        headed=False,
        vnc=False,
        browser="chromium",
        report_url=None,
        href_target="_blank",
        registry_username=None,
        registry_password=None,
        s3_endpoint=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        s3_report_bucket=None,
        s3_report_path=None,
        s3_report_url=None,
        loki_endpoint=None,
        loki_user=None,
        loki_password=None,
        loki_proxy=None,
        current_status=None,
    )
    defaults.update(overrides)
    return RunConfig(**defaults)


def make_ctx(**overrides) -> RunContext:
    """Build a RunContext with sensible test defaults. Override any field by name."""
    defaults = dict(
        hostname="testhost",
        servicedescription="TestService",
        testname="testhost/TestService",
        testident="testhost__TestService",
        container_name="testhost_TestService",
        start_time=1700000000.0,
        started_str="1700000000",
        timeout_deadline=1700000060.0,
        result_dir="/tmp/test_results",
        omd_root="",
        pid_file="/tmp/var/tmp/check_cep.testhost__TestService.pid",
        config=make_config(),
    )
    defaults.update(overrides)
    return RunContext(**defaults)
