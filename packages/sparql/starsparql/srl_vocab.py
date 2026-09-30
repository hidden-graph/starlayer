"""The RDF vocabulary for the SRL/SPARQL-RL abstract syntax (``srl:``).

SRL ("a Datalog-style rules language for RDF", `WD-sparql12-rl-20260919
<https://www.w3.org/TR/sparql12-rl/>`_) is its own general-purpose,
SHACL-independent rules language, published by the W3C Data Shapes WG but
with no stated compilation target into ``sh:rule``/``sh:TripleRule`` — see
``packages/shacl/docs/shacl12-gap-matrix.md``'s "Not Covered / Deferred"
entry for the spec-status writeup. This mirrors ``ast_vocab.py``'s
``sast:`` design (generic ``node -> rdf:type``, field -> predicate,
recursively) but points at SRL's own §4.1 abstract syntax tree
(``starsparql.srl_ast``) rather than a raw rdflib parse tree — there is no
``CompValue`` involved on the SRL side at all, since SRL text never feeds
rdflib's own algebra/translate machinery.

Field names below are taken **verbatim** from the spec's own §4.1
"Component Notation" table, not invented — e.g. ``rule.head``/``rule.body``/
``rule.data``/``rule.id``, ``ruleset.rules``/``ruleset.data``/
``ruleset.imports``, ``filter.expr``, ``assign.var``/``assign.expr``,
``negation.inner``/``negation.data``. Unlike ``from_rdf.py``'s empirically-
derived ``_LIST_VALUED_KEYS`` (needed there because rdflib's own algebra
shapes aren't documented anywhere as exhaustively as this), which fields
are list-valued is already fully known from the spec text and stated
directly, not derived by testing.

List-valued fields (encoded as ``rdf:List``, via ``rdflib.collection
.Collection`` — same convention ``to_rdf.py`` uses):
  ``ruleset.rules``, ``ruleset.data``, ``ruleset.imports``,
  ``rule.head`` (a sequence of triple templates),
  ``rule.body`` (a sequence of rule elements),
  ``negation.inner`` (a sequence of rule elements, restricted to triple
  patterns + filters by the grammar — see ``srl_ast.NegationElement``),
  ``data.triples`` (a sequence of ground triples).

Scalar fields: ``rule.data`` (bool), ``rule.id`` (an IRI or absent),
``filter.expr``/``assign.expr`` (a SPARQL 1.2 expression tree — reuses
``salg:`` expression encoding directly, see below), ``assign.var``,
``negation.data`` (bool), each triple (pattern/template)'s own
``srl:subject``/``srl:predicate``/``srl:object``.

Reused, not re-minted, from the sibling ``salg:``/``sast:`` vocabularies —
same reasoning ``ast_vocab.py``'s own docstring gives for ``PyStr``/
``Variable``: these are pure encoding-primitive tags, not concepts that
differ in meaning by layer, so reusing them keeps the same Python value
round-tripping identically (and comparably, via plain term equality)
regardless of which layer encoded it:
  - ``salg:Variable``/``salg:PyStr`` datatypes (``vocab.VARIABLE_DATATYPE``/
    ``PY_STR_DATATYPE``) for SRL's own ``Var``/bare-Python-value leaves.
  - A ``filter.expr``/``assign.expr`` expression tree is encoded with
    ``to_rdf.py``'s existing generic ``salg:``-namespaced CompValue encoder
    directly (``to_rdf._encode``/``from_rdf._decode``) — SRL's own grammar
    (``srl_grammar.py``) parses expressions by reusing rdflib's real
    ``Expression`` production unmodified, so the resulting tree is an
    ordinary rdflib ``Expr``/``CompValue`` tree, already exactly what
    ``to_rdf.py`` knows how to encode. No new expression vocabulary is
    minted under ``srl:`` at all.
  - A triple term appearing inside an SRL triple pattern/template
    (``starsparql.triple_term.TripleTermNode``) is likewise encoded via
    ``to_rdf.py``'s existing generic encoder, not re-implemented here.
"""

from __future__ import annotations

from rdflib import Namespace

SRL = Namespace("https://github.com/hidden-graph/starsparql/ns/srl#")

# Root marker for the resource holding a parsed rule set, in addition to
# its own srl:RuleSet typing (matches vocab.QUERY / ast_vocab.QUERY's
# "typed twice" convention: once generically by the encoder, once as an
# explicit named constant other code can grep for).
RULE_SET = SRL.RuleSet

RULE = SRL.Rule
DATA_BLOCK = SRL.Data
TRIPLE_PATTERN = SRL.TriplePattern
FILTER_ELEMENT = SRL.FilterElement
NEGATION_ELEMENT = SRL.NegationElement
ASSIGNMENT_ELEMENT = SRL.AssignmentElement

# srl:subject/predicate/object deliberately reuse the exact same local
# names as salg:TriplePattern's own three predicates (vocab.py's
# TRIPLE_PATTERN_SUBJECT/_PREDICATE/_OBJECT) - same structural shape
# (three term slots), just under the srl: namespace since an SRL triple
# pattern/template is its own AST node, not a salg: one.
TRIPLE_SUBJECT = SRL.subject
TRIPLE_PREDICATE = SRL.predicate
TRIPLE_OBJECT = SRL.object

# List-valued fields (rdf:List) - see module docstring.
RULES = SRL.rules
DATA = SRL.data
IMPORTS = SRL.imports
HEAD = SRL.head
BODY = SRL.body
INNER = SRL.inner
TRIPLES = SRL.triples

# Scalar fields. The spec reuses the bare name "data" for two different
# components (rule.data: a boolean "match against a DATA block" flag;
# ruleset.data: a list of Data blocks; negation.data: another boolean flag)
# - each gets its own predicate URI here rather than sharing SRL.data with
# the list-valued RULES/DATA above, to avoid a real same-URI-different-shape
# collision within one shared graph.
RULE_DATA_FLAG = SRL.ruleData
RULE_ID = SRL.id
EXPR = SRL.expr
VAR = SRL.var
NEGATION_DATA_FLAG = SRL.negationData
