"""
starlayer.graph.graph._timeout

A general wall-clock timeout for OWL-DL reasoning calls
(`infer(profile=ENTAILMENT["OWL-Direct"], engine=...)`, either engine) - defense-in-depth
against a hang no pre-flight structural check has been written for yet.
`owl_dl_rustdl.py`'s own `_check_rustdl_hang_risk()` covers one known,
specific hang pattern (fast, a few milliseconds, a clear "here's exactly
what's wrong" message); this covers everything else, for either engine,
known pattern or not - the two are complementary, not alternatives to
each other.

**Why a subprocess, not a thread + `signal.alarm()`/`threading.Event`:**
the actual blocking call in each engine is either a JVM subprocess wait
(HermiT, via `owlready2.sync_reasoner()`) or an opaque, uninterruptible
native PyO3 call with no Python bytecode execution in between it and
whatever it's doing internally (RustDL). Neither reliably yields back to
Python's own interpreter loop for a signal handler to fire, and a
background *thread* running either one can't actually be killed from
Python once started - only the *caller* gives up waiting on it; the
thread, and whatever it's blocked on, keep running (and consuming
CPU/memory/a JVM child process) indefinitely in the background regardless.
The only reliable way to bound an opaque, uninterruptible blocking call is
OS-level process termination.

**Why a full process *group* kill, not just the immediate child:**
HermiT's own call chain is Python -> owlready2 (the subprocess this module
spawns) -> a further `java` subprocess owlready2 launches itself. Killing
only the immediate child leaves that `java` grandchild running, orphaned,
still consuming resources indefinitely - exactly the orphaned-process bug
class already found and fixed elsewhere in this project. `run_with_timeout()`
makes the child call `os.setpgrp()` as its very first action (before doing
any real work), making it - and therefore anything it further spawns -
the leader of a brand-new process group distinct from the parent's;
`os.killpg()` on timeout then reliably takes the whole tree down with one
signal, not just the direct child.

**POSIX only** (`os.setpgrp`/`os.killpg` have no Windows equivalent) - the
same implicit scope every other subprocess-based piece of this codebase
already has (e.g. `shutil.which("java")`-style checks are portable, but
process-group semantics are not); not something this project has taken on
Windows support for elsewhere either.

**`multiprocessing`'s "spawn" start method, explicitly, not the platform
default:** deterministic across macOS/Linux rather than relying on
whichever start method happens to be each platform's own default (macOS
has used "spawn" as its own default since Python 3.8 specifically because
"fork" is documented as unsafe once certain system libraries - notably
anything Objective-C-runtime-adjacent - have already been loaded; forking
a process that may have JVM/native library state loaded is a related,
real risk this module has no reason to accept just because some other
platform's default might still be "fork"). The cost is that `target` must
be picklable by reference (a real module-level function, not a
closure/lambda) - already true of every caller in this codebase.
"""

from __future__ import annotations

import multiprocessing
import os
import signal
import time
from typing import Any, Callable
from starlayer.graph.graph.entailment_regimes import ENTAILMENT

DEFAULT_TIMEOUT_SECONDS = 120.0

_CTX = multiprocessing.get_context('spawn')


class ReasoningTimeoutError(RuntimeError):
    """Raised when an OWL-DL reasoning call (either engine) exceeds its
    wall-clock budget and had to be forcibly killed - see this module's
    own docstring for why a hard process-group kill, not a cooperative
    cancellation, is the only mechanism available here."""


def _trampoline(target: Callable[..., None], args: tuple, queue) -> None:
    """Runs inside the child process, before `target` itself. `os.setpgrp()`
    here - not left to `target` to remember - is what makes the
    process-group kill below actually work; centralizing it here means no
    future `target` implementation can forget it and silently reintroduce
    the orphaned-JVM-process bug this module exists to prevent."""
    os.setpgrp()
    target(*args, queue)


def run_with_timeout(target: Callable[..., None], args: tuple, timeout_seconds: float | None) -> tuple:
    """Run `target(*args, queue)` in a fresh child process (its own
    process group) with a hard wall-clock budget.

    `target` must be a module-level (picklable-by-reference) function that
    does its own work and puts exactly one result tuple onto `queue` when
    done - this function itself never inspects the *content* of that
    tuple (each engine's own module defines its own small result-status
    protocol), only whether one arrived before the deadline.

    `timeout_seconds=None` disables the timeout entirely (waits
    indefinitely, the pre-this-feature behavior) - an explicit opt-out,
    not the default; every real caller in this codebase passes
    `DEFAULT_TIMEOUT_SECONDS` unless the caller of *that* overrides it.

    Returns whatever `target` put on the queue. Raises
    ReasoningTimeoutError (after killing the child's entire process group)
    if nothing arrives within `timeout_seconds`.
    """
    queue: Any = _CTX.Queue()
    process = _CTX.Process(target=_trampoline, args=(target, args, queue))
    process.start()

    try:
        if timeout_seconds is None:
            result = queue.get()
        else:
            deadline = time.monotonic() + timeout_seconds
            result = None
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    result = queue.get(timeout=min(remaining, 0.5))
                    break
                except Exception:
                    # queue.Empty on this poll slice - keep waiting until
                    # the deadline, or until the child dies without ever
                    # producing a result (a crash, not a hang - stop
                    # waiting the moment that's true rather than idling
                    # out the full budget for no reason).
                    if not process.is_alive():
                        break
                    continue

        if result is not None:
            return result

        if not process.is_alive():
            raise ReasoningTimeoutError(
                'OWL-DL reasoning subprocess exited without producing a result '
                '(likely crashed) - see the subprocess for details; this is not '
                'a wall-clock timeout, but the failure mode looks the same from '
                'here since nothing was returned to inspect.'
            )

        raise ReasoningTimeoutError(
            f'OWL-DL reasoning did not complete within {timeout_seconds}s and was '
            'forcibly terminated. The reasoner may be stuck on a pathological '
            'input, or the ontology may simply be larger/more complex than this '
            'budget allows - retry with a larger timeout= if the latter, or file '
            'an issue with a minimal reproduction if a specific construct seems '
            'responsible (docs/future_enhancements.md tracks the one already-known '
            'RustDL hang pattern, caught earlier by a fast pre-flight check rather '
            'than ever reaching this timeout).'
        )
    finally:
        if process.is_alive():
            _kill_process_group(process.pid)
            process.join(timeout=5)
        else:
            process.join(timeout=5)
        queue.close()


def _kill_process_group(pid: int) -> None:
    """SIGKILL the entire process group rooted at `pid` (which is a valid
    process-group ID only because `_trampoline` above called
    `os.setpgrp()` as the child's first action) - not just `pid` itself -
    so a JVM (or other) grandchild the reasoning call spawned is never
    left orphaned and running. Safe to call on an already-dead process."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
