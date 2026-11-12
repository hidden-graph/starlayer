"""A pyoxigraph ``QuadIter`` is ``unsendable``: dropped on another thread than the one that made it, it raises ``RuntimeError`` and, on
a garbage-collection path, can take the whole process down. A graph's lazy readers (``objects``, ``triples``, ``quads`` ...) that a
caller does not exhaust (``next(g.objects(s, p), None)``) are finalised by whichever thread runs the cyclic GC, so apps that serve
requests on worker threads crashed at random. The checks run in a subprocess because the failure is a process crash."""

import subprocess
import sys
import textwrap

import pytest

SCRIPT = textwrap.dedent(
    """
    import gc, sys, threading
    from starlayer import StarLayerGraph, StarLayerDataset

    N = int(sys.argv[1])
    g = StarLayerGraph()
    g.parse(data="@prefix ex: <http://example.org/> . " + " ".join(f"ex:s{i} ex:p ex:o{i} ." for i in range(N)), format="turtle")
    d = StarLayerDataset()
    d.parse(data="@prefix ex: <http://example.org/> . " + " ".join(f"ex:s{i} ex:p ex:o{i} ." for i in range(N)), format="turtle")
    view = g.engine_view()
    box = []
    errors = []
    sys.unraisablehook = lambda u: errors.append(repr(u.exc_value))
    sys.excepthook = lambda *a: errors.append(repr(a[1]))
    threading.excepthook = lambda a: errors.append(repr(a.exc_value))

    def make():
        for _ in range(50):
            for it in (
                g.objects(None, None), g.subjects(None, None), g.predicates(None, None), g.triples((None, None, None)),
                g.quads((None, None, None, None)), iter(g), g.subject_objects(None), d.quads((None, None, None, None)),
                view.triples((None, None, None)), view.objects(None, None), g.reifiers(),
            ):
                next(it, None)
                box.append(it)

    t = threading.Thread(target=make); t.start(); t.join()

    def drop():
        box.clear()
        gc.collect()

    t = threading.Thread(target=drop); t.start(); t.join()
    gc.collect()
    sys.unraisablehook = sys.__unraisablehook__  # (what interpreter shutdown then reports goes to stderr)
    if errors:
        print("ERRORS", errors[:3]); sys.exit(3)
    print("survived")
    """
)


@pytest.mark.parametrize("size", [200, 5000], ids=["small results", "results larger than one read-ahead chunk"])
def test_unexhausted_readers_dropped_by_another_thread_do_not_crash(size):
    run = subprocess.run([sys.executable, "-c", SCRIPT, str(size)], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, (run.returncode, run.stdout[-600:], run.stderr[-600:])
    assert run.stderr.strip() == "" and run.stdout.strip().endswith("survived")


REPRO = textwrap.dedent(
    """
    import threading, gc
    from starlayer import StarLayerGraph
    g = StarLayerGraph(); g.parse(data="@prefix ex: <http://example.org/> . " + " ".join(f"ex:s{i} ex:p ex:o{i} ." for i in range(200)), format="turtle")
    box = []
    def make():
        for _ in range(200):
            it = g.objects(None, None)
            next(it, None)
            box.append(it)
    t = threading.Thread(target=make); t.start(); t.join()
    def drop():
        box.clear(); gc.collect()
    t = threading.Thread(target=drop); t.start(); t.join()
    print("survived")
    """
)


def test_a_reader_left_by_a_finished_thread_is_silent_at_interpreter_exit():
    run = subprocess.run([sys.executable, "-c", REPRO], capture_output=True, text=True, timeout=300)
    assert (run.returncode, run.stdout.strip(), run.stderr.strip()) == (0, "survived", "")
