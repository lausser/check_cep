"""Collision detection test: two simultaneous check_cep calls for the same
host/service — one must be blocked immediately."""
import threading
import time

from conftest import run_check_cep, local_test_dir, _container_rm


def test_collision(tmp_path, write_playwright_config):
    """Instance B is blocked within 5 s when instance A is still running."""
    # Use tc_timeout with --timeout 30 so instance A is guaranteed to be
    # running when instance B starts (deterministic collision window).
    test_dir = local_test_dir(tmp_path, "tc_timeout", write_playwright_config)

    common_args = [
        "--host-name", "testhost",
        "--service-description", "collision_test",
        "--timeout", "30",
    ]

    # Both instances MUST share the same result_dir so they see the same PID file.
    # The PID file path is result_dir/running_{testident}; different dirs mean
    # different PID files and no collision is detected.
    shared_rd = tmp_path / "results"

    results = {}
    timings = {}

    def run(label):
        start = time.monotonic()
        output, code = run_check_cep(
            test_dir,
            shared_rd,
            extra_args=common_args,
            proc_timeout=90,
        )
        elapsed = time.monotonic() - start
        results[label] = (output, code)
        timings[label] = elapsed

    t_a = threading.Thread(target=run, args=("a",))
    t_b = threading.Thread(target=run, args=("b",))

    t_a.start()
    # Give instance A 2 s to acquire the PID file before B starts
    time.sleep(2)
    t_b.start()

    t_a.join(timeout=90)
    t_b.join(timeout=90)

    output_a, code_a = results["a"]
    output_b, code_b = results["b"]

    # One instance should have been blocked (duplicate/already running)
    blocked = None
    normal = None
    for label, (output, code) in results.items():
        if "duplicate" in output.lower() or "already running" in output.lower():
            blocked = label
        else:
            normal = label

    assert blocked is not None, (
        "Neither instance reported a collision.\n"
        f"A (exit {code_a}): {output_a[:300]}\n"
        f"B (exit {code_b}): {output_b[:300]}"
    )

    # The blocked instance must have exited quickly (within 5 s of starting)
    assert timings[blocked] < 10, (
        f"Blocked instance took {timings[blocked]:.1f}s — expected < 10s"
    )

    # After both finish, a third sequential call must succeed normally
    output_c, code_c = run_check_cep(
        test_dir,
        shared_rd,
        extra_args=common_args,
        proc_timeout=90,
    )
    assert "duplicate" not in output_c.lower(), (
        f"Third sequential call falsely reported collision.\nOutput: {output_c[:300]}"
    )

    # Clean up container-owned (sub-UID) files that pytest cannot remove
    _container_rm([shared_rd])
