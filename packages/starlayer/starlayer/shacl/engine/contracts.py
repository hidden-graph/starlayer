from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ComponentRequest:
    """One native-component evaluation request - ``evaluate_component()``'s
    own sole argument.
    """

    component: Any
    focus_node: Any
    value_nodes: tuple[Any, ...]
    options: dict[str, Any] = field(default_factory=dict)
