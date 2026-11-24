"""Warnings that name the caller's line, not a line inside StarLayer."""

from __future__ import annotations

import os
import sys
import warnings

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__)) + os.sep


def warn_at_caller(message: str, category: type[Warning]) -> None:
    """``warnings.warn`` attributed to the first frame outside the ``starlayer`` package, whatever the entry point's call depth."""
    level, frame = 2, sys._getframe(1)  # level 1 is this function; 2 is the function that called it
    while frame is not None and os.path.abspath(frame.f_code.co_filename).startswith(_PACKAGE_DIR):
        frame, level = frame.f_back, level + 1
    warnings.warn(message, category, stacklevel=level)
