"""Manchester syntax for ``StarLayerGraph.parse`` / ``serialize``: the parser and the serializer.

Malformed text is a ``FormatError`` of kind ``"manchester"`` (``why``, ``line``; ``col`` and ``pos`` where known), RDF that is not valid OWL a
``FormatError`` of kind ``"owl"``, a class expression nested too deeply an ``ExecutionError`` of kind ``"nesting"``, and a graph Manchester
syntax cannot write an ``ExecutionError`` of kind ``"unsupported"``.

The ``manch:`` tree functions (parse to a syntax-tree graph, validate, edit) are in ``starlayer.starontology.manchester``.
"""
