"""Tests for starlayer.graph.graph._timeout - the general wall-clock
timeout mechanism `infer(profile="owl-dl", timeout=...)`/
`query(entailment="direct", timeout=...)` share across both reasoning
engines. Uses synthetic worker functions, not real HermiT/RustDL calls -
the mechanism (subprocess spawn, deadline, process-group kill) is what's
under test here, independent of any specific reasoner; engine-specific
wiring (does infer()/query() actually pass timeout= through correctly) is
covered separately in test_infer_owl_dl.py/test_infer_owl_dl_rustdl.py.

Worker functions are module-level (not closures/lambdas) because
`multiprocessing`'s "spawn" start method needs them picklable by
reference - see _timeout.py's own module docstring for why "spawn" is
used deliberately, not left to the platform default.
"""

import os
import subprocess
import sys
import time

import pytest

from starlayer.graph.graph._timeout import ReasoningTimeoutError, run_with_timeout


def _fast_worker(x, queue):
    queue.put(('ok', x * 2))


def _raising_status_worker(queue):
    """Simulates a real engine's own "found a real problem, not a hang"
    path - puts an error status on the queue instead of raising a bare
    exception (matching owl_dl.py/owl_dl_rustdl.py's own contract: the
    worker always puts exactly one tuple on queue, never lets an
    exception cross the process boundary uncaught)."""
    queue.put(('some_error', 'a real, non-hang failure'))


def _crashing_worker(queue):
    """Never puts anything on queue at all - simulates a genuine crash
    (as opposed to a hang) in the child. run_with_timeout() must not wait
    out the full budget once the process has actually died."""
    raise RuntimeError('simulated crash - never touches queue')


def _hang_worker(queue):
    time.sleep(600)
    queue.put(('ok', 'unreachable'))


def _hang_with_grandchild_worker(marker_path, queue):
    """Simulates HermiT's own shape: this child spawns a further real OS
    subprocess (standing in for `java`) that must also die when the
    process group is killed - the specific failure mode this whole
    process-group (not just single-process) design exists to prevent."""
    subprocess.Popen([
        sys.executable, '-c',
        f'import time, pathlib; pathlib.Path({marker_path!r}).write_text("alive"); time.sleep(600)',
    ])
    time.sleep(600)


class TestRunWithTimeoutHappyPath:
    def test_fast_worker_returns_its_result(self):
        result = run_with_timeout(_fast_worker, (21,), timeout_seconds=10)
        assert result == ('ok', 42)

    def test_timeout_none_waits_indefinitely_for_a_fast_worker(self):
        result = run_with_timeout(_fast_worker, (5,), timeout_seconds=None)
        assert result == ('ok', 10)

    def test_worker_supplied_error_status_passes_through(self):
        result = run_with_timeout(_raising_status_worker, (), timeout_seconds=10)
        assert result == ('some_error', 'a real, non-hang failure')


class TestRunWithTimeoutFailureModes:
    def test_hang_raises_reasoning_timeout_error_near_the_deadline(self):
        t0 = time.monotonic()
        with pytest.raises(ReasoningTimeoutError):
            run_with_timeout(_hang_worker, (), timeout_seconds=1.5)
        elapsed = time.monotonic() - t0
        # Generous bounds - process spawn overhead varies, but this must
        # not have waited anywhere near the 600s the worker itself sleeps.
        assert 1.0 < elapsed < 15.0, f'timing looks wrong: {elapsed}s'

    def test_crashed_child_raises_promptly_not_after_the_full_budget(self):
        t0 = time.monotonic()
        with pytest.raises(ReasoningTimeoutError):
            run_with_timeout(_crashing_worker, (), timeout_seconds=30)
        elapsed = time.monotonic() - t0
        assert elapsed < 15.0, (
            f'took {elapsed}s to notice a dead process - should be prompt, '
            'not wait out the full 30s timeout budget'
        )

    def test_grandchild_process_does_not_survive_the_timeout_kill(self, tmp_path):
        """The specific case this whole process-*group* design exists for:
        a JVM-like grandchild process must not be left orphaned and
        running after the parent's timeout kills the child."""
        marker_path = str(tmp_path / 'marker.txt')
        with pytest.raises(ReasoningTimeoutError):
            run_with_timeout(_hang_with_grandchild_worker, (marker_path,), timeout_seconds=2)

        deadline = time.monotonic() + 5
        while not os.path.exists(marker_path) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert os.path.exists(marker_path), (
            'grandchild process never even started - this test is not '
            'actually proving anything'
        )

        time.sleep(1)  # let the SIGKILL actually land
        ps_out = subprocess.run(['ps', 'aux'], capture_output=True, text=True).stdout
        lingering = [
            line for line in ps_out.splitlines()
            if 'time.sleep(600)' in line and 'grep' not in line
        ]
        assert not lingering, f'a grandchild process survived the process-group kill: {lingering}'
