"""rule_set= and include_source_rule_provenance= still apply to sh:TripleRule in a fresh process (GitHub issue #104).

Installing the TripleRule patch from register_native_components() replaced the function apply_rules() had just wrapped for
rule-set filtering and provenance, so both were silently ignored; the order only shows in a process that has not validated yet.
"""

import subprocess
import sys
import textwrap

SCRIPT = textwrap.dedent(
    """
    import warnings; warnings.simplefilter('ignore')
    from rdflib import URIRef
    from starlayer.graph import StarLayerGraph
    from starlayer.shacl import StarShaclSchema
    P = '@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex/> . '
    s = StarLayerGraph()
    s.parse(data=P + 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule ex:RA, ex:RB . ex:RuleSetA a sh:RuleSet ; sh:hasRule ex:RA . '
            'ex:RA a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:ta ; sh:object 1 . '
            'ex:RB a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:tb ; sh:object 1 .', format='turtle12')
    d = StarLayerGraph()
    d.parse(data=P + 'ex:a ex:z 0 .', format='turtle12')
    r = StarShaclSchema(shacl_graph=s).apply_rules(
        data_graph=d, meta_shacl=False, rule_set=URIRef('http://ex/RuleSetA'), include_source_rule_provenance=True)
    preds = sorted(str(p).rsplit('/', 1)[-1] for _s, p, _o in r.inferred_graph)
    print(preds)
    """
)


def test_rule_set_and_provenance_apply_to_triple_rules_in_a_fresh_process():
    out = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, check=True).stdout
    assert "'ta'" in out
    assert "'tb'" not in out
    assert "sourceRule" in out
