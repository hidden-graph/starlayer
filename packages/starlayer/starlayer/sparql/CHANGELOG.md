# Changelog

## Unreleased

- Added full SRL/SPARQL-RL support (`WD-sparql12-rl-20260919`): a real pyparsing grammar (`srl_grammar.py`/`srl_ast.py`), a `srl:` AST-as-RDF namespace with a full round trip (`srl_vocab.py`/`srl_to_rdf.py`/`srl_from_rdf.py`), structural SHACL shapes (`ontology/srl_shapes.py`, registered as `srl_owl`/`srl_shacl`), the §4.2 well-formedness check (`srl_semantic_checks.py`), and a stratified Datalog evaluation engine (`srl_eval.py`) verified end to end against the spec's own §6.6 worked example.
