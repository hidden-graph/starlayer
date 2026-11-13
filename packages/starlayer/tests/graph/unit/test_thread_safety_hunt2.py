"""Concurrent SPARQL parsing and evaluation (GitHub issue #100)."""

import subprocess
import sys
import textwrap
import warnings
from concurrent.futures import ThreadPoolExecutor

from starlayer.graph import StarLayerGraph

warnings.simplefilter("ignore")

COLD_START = textwrap.dedent(
    """
    import warnings; warnings.simplefilter('ignore')
    from concurrent.futures import ThreadPoolExecutor
    from starlayer.graph import StarLayerGraph
    g = StarLayerGraph()
    g.parse(data='@prefix : <http://e/> . :s :p 1 . :t :p 2 .', format='turtle12')
    Q = 'PREFIX : <http://e/> SELECT ?s WHERE { ?s :p ?o FILTER(?o > %d) }'
    def run(i):
        try:
            return len(list(g.query(Q % (i % 2))))
        except Exception as e:
            return 'ERR ' + str(e)[:80]
    with ThreadPoolExecutor(8) as ex:
        print(sorted({str(r) for r in ex.map(run, range(60))}))
    """
)


def test_the_first_queries_of_a_process_can_run_in_worker_threads():
    out = subprocess.run([sys.executable, "-c", COLD_START], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "['1', '2']"


def test_concurrent_evaluation_of_one_cached_query_gives_the_right_rows():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://e/> . " + " ".join(f":s{i} :p {i} ." for i in range(30)), format="turtle12")
    queries = [f"PREFIX : <http://e/> SELECT ?s WHERE {{ ?s :p ?o FILTER(?o >= {k}) }}" for k in (0, 10, 20)]
    g.query(queries[0])  # settle the grammar in this thread

    def count(k):
        return len(list(g.query(queries[k % 3])))

    with ThreadPoolExecutor(8) as pool:
        counts = list(pool.map(count, range(90)))
    assert counts == [30 - 10 * (k % 3) for k in range(90)]
