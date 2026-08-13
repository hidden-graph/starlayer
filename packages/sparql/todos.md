are we aligned with the algebraix syntax in the https://www.w3.org/TR/sparql12-query/?utm_source=chatgpt.com#algebraicSyntax


Things to prove:
1. any valid SPARQL 1.2 query should be able to trnasformed into rdf/algebra and reconstitured.
2. transform our 1.2 algebra into a 1.1 starlayergraph algebra that rdlib undestands. 






Notes about overall structure:
rdflib-star:
    Core engine: management of rdf1.2 graphs
    Sparql engine: 1
    - translate 1.2 queries into and out of 1.2 algebra
    - translate 1.2 algebra into 1.1 algebra for use with starlayergraph graph
    - run query against in-memory and various backends
pyshacl-star:
    -  shacl 1.2 working with rdf 1.2 graphs
kg explorer:
    - graph exploerer/editor
    - owl axioms
    - sparql editor
    - shacl editor
    - skos editor
    - inferencing

