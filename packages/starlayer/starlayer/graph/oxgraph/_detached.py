"""Store iterators that no thread but their own ever drops.

A pyoxigraph ``QuadIter`` is ``unsendable``: dropped on another thread than the one that made it, it raises ``RuntimeError`` and, when
that happens inside the cyclic GC, can end in a segfault of the whole process. A lazy reader a caller does not exhaust
(``next(g.objects(s, p), None)``) is finalised by whichever thread runs the GC, so ``detached`` reads a store iterator in chunks
on the creating thread and keeps the iterator itself only while results remain. Results shorter than one chunk (the usual
lookup) never hold it past the call. A longer, abandoned or foreign-thread-finished iteration parks its iterator in ``_PARKED``
(kept alive, not dropped) for the creating thread to drop on its next read; if that thread is gone, the iterator leaks.
Chunks keep a full scan at C speed apart from one Python call per chunk.
"""

from __future__ import annotations

import atexit
import ctypes
import threading
from collections import deque
from collections.abc import Iterator
from itertools import chain, islice
from typing import Any

_FIRST = 64  # (a lookup's results, mostly: a lookup that fits one chunk holds no store iterator at all)
_MAX = 8192
_PARKED: deque[tuple[threading.Thread, Any]] = deque()


def _drop_parked() -> None:
    me = threading.current_thread()
    for _ in range(len(_PARKED)):
        try:
            entry = _PARKED.popleft()
        except IndexError:
            return
        if entry[0] is not me:
            _PARKED.append(entry)
        entry = None  # (dropped here, on the thread that made it)


def _leak_parked_at_exit() -> None:
    """Interpreter teardown drops module globals on the main thread, which would raise for an iterator another thread made: keep a
    reference to each for good (the process is ending)."""
    _drop_parked()
    for _owner, it in list(_PARKED):
        ctypes.pythonapi.Py_IncRef(ctypes.py_object(it))


atexit.register(_leak_parked_at_exit)


class _Chunks:
    """The remaining results as lists; owns the store iterator and releases it on exhaustion, close or finalisation."""

    __slots__ = ("_it", "_owner", "_head", "_size")

    def __init__(self, it: Any, head: list) -> None:
        self._it = it
        self._owner = threading.current_thread()  # (not its ident: a finished thread's ident is reused by the next one)
        self._head: list | None = head
        self._size = _FIRST * 4

    def __iter__(self) -> _Chunks:
        return self

    def __next__(self) -> list:
        head = self._head
        if head is not None:
            self._head = None
            return head
        it = self._it
        if it is None:
            raise StopIteration
        chunk = list(islice(it, self._size))
        if len(chunk) < self._size:
            it = None
            self._release()
        self._size = min(self._size * 4, _MAX)
        if not chunk:
            raise StopIteration
        return chunk

    def _release(self) -> None:
        it, self._it = self._it, None
        if it is not None and threading.current_thread() is not self._owner:
            _PARKED.append((self._owner, it))

    def __del__(self) -> None:
        self._release()


def detached(it: Any) -> Iterator[Any]:
    """``it`` (a pyoxigraph store iterator, just made on this thread) as an iterator that is safe to abandon or finish on any thread."""
    if _PARKED:
        _drop_parked()
    head = list(islice(it, _FIRST))
    if len(head) < _FIRST:
        return iter(head)
    return chain.from_iterable(_Chunks(it, head))
