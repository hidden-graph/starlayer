"""Native SHACL 1.2 engine (branch ``shacl-engine``): no pyshacl, no rdflib object model in the core.

See ``docs/working/shacl-engine-design.md``. ``validate()`` is the entry point; ``starlayer.shacl`` keeps working beside
it as the differential oracle until cut-over.
"""

from starlayer.shacl_engine.api import validate

__all__ = ["validate"]
