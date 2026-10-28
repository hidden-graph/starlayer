"""Build each constraint component once per shape, not once per focus node.

pySHACL's ``Shape.validate()`` runs ``c = constraint_component(self)`` on every call, and a property shape is validated once
for each focus node of its node shape. A component's ``__init__`` reads its parameters from the shapes graph (a ``sh:in``
list is walked to its end, ``sh:or`` members are looked up, a ``sh:pattern`` is compiled), so the same work was repeated for
every node: a 1,000-value ``sh:in`` list over 200 nodes cost 200 walks of the list, 12 s against 1 s for a 10-value list.

This wraps ``__init__`` of every class in pySHACL's ``CONSTRAINT_PARAMETERS_MAP`` so that the first construction for a shape
records the instance's attributes and later constructions for the same shape copy them back. The record lives on the
``ShapesGraph``, which is rebuilt for each validation, so nothing is kept between validations and a changed shapes graph is
never served from it. No pySHACL or StarLayer component assigns to ``self`` while evaluating, so sharing the attribute
values (a set, a compiled pattern) between instances is safe. A construction that raises is not recorded and raises again.

Process-global and idempotent, like the other pySHACL patches.
"""

from __future__ import annotations

import functools

_SENTINEL = "_starlayer_shacl_component_cache_patch"
_CACHE_ATTR = "_starlayer_component_cache"
_DEPTH_ATTR = "_starlayer_component_init_depth"


def _cached(original):
    @functools.wraps(original)
    def __init__(self, shape, *args, **kwargs):
        sg = getattr(shape, "sg", None)
        store = getattr(sg, "__dict__", None)
        if args or kwargs or store is None or not hasattr(self, "__dict__"):
            return original(self, shape, *args, **kwargs)
        cache = store.setdefault(_CACHE_ATTR, {})
        key = (id(shape), type(self))
        entry = cache.get(key)
        if entry is not None and entry[0] is shape:
            self.shape = shape
            self.__dict__.update(entry[1])
            return None
        depth = self.__dict__.get(_DEPTH_ATTR, 0)
        self.__dict__[_DEPTH_ATTR] = depth + 1
        try:
            original(self, shape)
        finally:
            self.__dict__[_DEPTH_ATTR] = depth
        if depth == 0:  # only the outermost __init__ has the finished state (a subclass calls super().__init__ first)
            state = {k: v for k, v in self.__dict__.items() if k != _DEPTH_ATTR}
            cache[key] = (shape, state)
        return None

    setattr(__init__, _SENTINEL, True)
    return __init__


def install_component_cache_patch() -> bool:
    """Wrap ``__init__`` of every registered constraint component class. True if installed or already installed."""
    try:
        from pyshacl.constraints import CONSTRAINT_PARAMETERS_MAP
        from pyshacl.constraints.constraint_component import ConstraintComponent
    except Exception:  # pragma: no cover - pyshacl missing or restructured: run unpatched
        return False
    for component_cls in set(CONSTRAINT_PARAMETERS_MAP.values()):
        if not (isinstance(component_cls, type) and issubclass(component_cls, ConstraintComponent)):
            continue
        init = component_cls.__init__
        if init is ConstraintComponent.__init__ or getattr(init, _SENTINEL, False):
            continue
        component_cls.__init__ = _cached(init)
    return True
