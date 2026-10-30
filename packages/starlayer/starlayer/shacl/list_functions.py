"""``sh:ListParameterExpressionFunction`` as a SPARQL function (SHACL 1.2 SPARQL Extensions 7.3, GitHub issue #176).

"SPARQL engines SHOULD register a function for each instance of ``sh:ListParameterExpressionFunction``": a function the shapes graph
declares can be called by its IRI from the SPARQL text of ``sh:select``, ``sh:ask`` and ``sh:construct``, as ``ex:spacedConcat('John', 'Doe')``.
The arguments become the scope of the body (``$arg0``, ``$arg1`` or ``[ shnex:arg 0 ]``, 6.1 and 7.1); the body is evaluated as a node
expression and must give one node. An error in the body is an error in the call (the SPARQL expression is unbound).

pySHACL registers the functions it knows (``sh:SPARQLFunction``) when validation starts and removes them when it ends; this adds the list
parameter functions to the same list (``gather_functions``), so they live exactly as long as the validation. Process-global and idempotent,
like the other pySHACL patches.
"""

from __future__ import annotations

from typing import Any

from rdflib import RDF, Namespace

SH = Namespace("http://www.w3.org/ns/shacl#")
_SENTINEL = "_starlayer_shacl_list_functions_patch"


class SparqlListFunction:
    """One list parameter function, registered with the SPARQL engine for the length of a validation."""

    def __init__(self, node: Any, sg: Any) -> None:
        self.node = node
        self.sg = sg

    def apply(self, g: Any) -> None:
        g.register_custom_function(self.node, self.execute_from_sparql, None, True, True)

    def unapply(self, g: Any) -> None:
        g.unregister_custom_function(self.node, self.execute_from_sparql, None)

    def execute_from_sparql(self, e: Any, ctx: Any) -> Any:
        from rdflib.plugins.sparql.sparql import SPARQLError

        from starlayer.shacl.node_expressions import eval_expr

        body = next(iter(self.sg.graph.objects(self.node, SH.bodyExpression)), None)
        if body is None:
            raise SPARQLError(f"The function {self.node} has no sh:bodyExpression.")
        scope: dict[Any, Any] = {}
        for index, argument in enumerate(e.expr or []):
            try:
                scope[index] = ctx[argument]
            except Exception as error:  # an unbound or erroring argument is an error in the call
                raise SPARQLError(f"Argument {index} of {self.node} has no value.") from error
        this = ctx.ctx.initBindings.get("this") if hasattr(ctx.ctx, "initBindings") else None
        scope["focusNode"] = this
        try:
            nodes = eval_expr(body, this, ctx.ctx.graph, self.sg, scope=scope)
        except Exception as error:
            raise SPARQLError(f"The body of {self.node} failed: {error}") from error
        if len(nodes) != 1 or nodes[0] is None:
            raise SPARQLError(f"The body of {self.node} gave {len(nodes)} nodes; a list parameter function gives one.")
        return nodes[0]


def install_list_function_patch() -> bool:
    """Make ``gather_functions`` also return the list parameter functions of the shapes graph. True if installed or already installed."""
    try:
        import pyshacl.validator as pyshacl_validator

        original = pyshacl_validator.gather_functions
        if getattr(original, _SENTINEL, False):
            return True

        def gather_functions(executor, shacl_graph):
            functions = list(original(executor, shacl_graph))
            for node in sorted(shacl_graph.graph.subjects(RDF.type, SH.ListParameterExpressionFunction), key=str):
                functions.append(SparqlListFunction(node, shacl_graph))
            return functions

        setattr(gather_functions, _SENTINEL, True)
        pyshacl_validator.gather_functions = gather_functions
        return True
    except Exception:
        return False
