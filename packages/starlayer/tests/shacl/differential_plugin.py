"""Pytest plugin: differential comparison of starlayer.shacl (pyshacl-backed) and starlayer.shacl_engine.

Enable with ``-p differential_plugin`` (put ``packages/starlayer/tests/shacl`` on PYTHONPATH) or
``-p tests.shacl.differential_plugin`` from ``packages/starlayer``. While the existing tests run unchanged, every call to
the old ``validate`` / ``StarShaclSchema.validate`` also runs the new engine on a private snapshot of the same
(data graph, shapes graph) and appends one JSON line to ``$DIFF_OUT`` (default
``docs/working/differential/results.jsonl`` under the repository root). The old call's return value, exceptions and the
test outcome are never changed. Graphs are snapshotted BEFORE the old call, so neither implementation can affect the
other's inputs.

Record fields: ``test``, ``kind`` (``validate`` or ``schema.validate``), ``outcome`` in {agree, differ, skipped,
engine_error, old_error}, plus ``skip_options`` (skipped), ``error`` (engine_error / old_error) and ``details`` (differ).
"""

from __future__ import annotations

import copy
import functools
import inspect
import json
import os
import signal
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

from rdflib import Graph

ENGINE_TIMEOUT_S = 20
MAX_SNIPPET_TRIPLES = 40

# validate() kwargs that do not change what the validation computes (or that the comparison handles itself).
# Options the engine's validate() accepts, passed through by _run_engine.
_ENGINE_OPTIONS = (
    "ont_graph",
    "inference",
    "meta_shacl",
    "meta_shapes_extra",
    "shapes_graph_loader",
    "ignore_imports",
    "shapes_graph_resource",
    "max_validation_depth",
    "abort_on_first",
    "data_graph_iri",
    "shapes_graph_iri",
    "specification_graph",
    "include_used_configuration",
)

_IGNORED = {
    "ignore_imports",
    "data_graph_iri",
    "shapes_graph_iri",
    "include_used_configuration",
    "specification_graph",
    "advanced",
    "allow_warnings",
    "allow_infos",
    "debug",
    "inplace",  # checked separately
    "meta_shacl",  # checked separately
    "inference",  # checked separately
    "mode",  # checked separately
    "decode_report",  # checked separately
    "meta_shapes_extra",  # checked separately
}

_state: dict[str, Any] = {"depth": 0, "out": None, "counts": Counter()}


class _Timeout(BaseException):
    pass


def _out_path() -> Path:
    env = os.environ.get("DIFF_OUT")
    if env:
        return Path(env)
    root = Path(__file__).resolve()
    for parent in root.parents:
        if (parent / ".git").exists():
            return parent / "docs" / "working" / "differential" / "results.jsonl"
    return Path("docs/working/differential/results.jsonl")


def _current_test() -> str:
    raw = os.environ.get("PYTEST_CURRENT_TEST", "")
    return raw.rsplit(" (", 1)[0] if raw else "<outside-test>"


def _write(record: dict[str, Any]) -> None:
    _state["counts"][record["outcome"]] += 1
    out = _state["out"]
    if out is None:
        return
    out.write(json.dumps(record, default=str) + "\n")
    out.flush()


def _snapshot(graph: Any) -> Any:
    """Copy a graph for the engine run, preserving literal lexical forms.

    copy.deepcopy rebuilds each Literal through its constructor, which
    rewrites "1"^^xsd:boolean to "true" (rdflib normalization), so the engine
    would see a different term than the old validator did. Copy the triples
    term-for-term into a graph of the same class instead.
    """
    if graph is None:
        return None
    try:
        clone = type(graph)()
        for prefix, ns in graph.namespaces():
            clone.bind(prefix, ns, override=True)
        for triple in graph.triples((None, None, None)):
            clone.add(triple)
        if len(clone) == len(graph):
            return clone
    except Exception:
        pass
    try:
        return copy.deepcopy(graph)
    except Exception:
        pass
    clone = Graph()
    for triple in graph.triples((None, None, None)):
        clone.add(triple)
    return clone


def _triple_count(graph: Any) -> int | None:
    try:
        return len(graph)
    except Exception:
        return None


def _skip_options(
    options: dict[str, Any], ont_graph: Any, validate_fn_custom: bool, resource: Any
) -> list[str]:
    skip: list[str] = []
    if validate_fn_custom:
        skip.append("validate_fn")
    # inference, ont_graph, meta_shacl, meta_shapes_extra, shapes_graph_loader, shapes_graph_resource,
    # max_validation_depth, abort_on_first and the provenance options are passed to the engine (see _run_engine).
    if options.get("inplace"):
        skip.append("inplace")
    if options.get("iterate_rules"):
        skip.append("iterate_rules")
    if options.get("decode_report") is False:
        skip.append("decode_report=False")
    if options.get("adapter") is not None:
        skip.append("adapter")
    if options.get("rdfs_subclass_reasoning_includes_shapes_graph"):
        skip.append("rdfs_subclass_reasoning_includes_shapes_graph")
    mode = options.get("mode")
    if mode is not None and str(getattr(mode, "name", mode)).lower() not in (
        "validation",
        "debug",
    ):
        skip.append(f"mode={getattr(mode, 'name', mode)}")
    for name in options:
        if name not in _IGNORED and name not in {
            "validate_fn",
            "adapter",
            "iterate_rules",
            "rdfs_subclass_reasoning_includes_shapes_graph",
            *_ENGINE_OPTIONS,
        }:
            skip.append(f"kwarg:{name}")
    return skip


def _disallows(options: dict[str, Any]) -> Any:
    from tests.shacl.w3c_shacl12.namespaces import SH

    if options.get("allow_warnings"):
        return SH.Violation
    if options.get("allow_infos"):
        return SH.Warning
    return None


def _short(key: Any, depth: int = 0) -> str:
    if key is None:
        return "-"
    if isinstance(key, tuple) and key and key[0] == "BNODE":
        if depth > 1:
            return "_:b{...}"
        inner = ", ".join(
            f"{p.rsplit('#', 1)[-1].rsplit('/', 1)[-1]}={_short(o, depth + 1)}"
            for p, o in key[1]
        )
        return "_:b{" + inner + "}"
    if isinstance(key, tuple) and key and key[0] == "TRIPLETERM":
        return "<<( " + " ".join(_short(part, depth + 1) for part in key[1:]) + " )>>"
    if isinstance(key, tuple) and key and key[0] == "LITERAL":
        return (
            repr(key[1])
            + (f"^^{key[2].rsplit('#', 1)[-1]}" if key[2] else "")
            + (f"@{key[3]}" if key[3] else "")
        )
    if isinstance(key, tuple) and key and key[0] == "URI":
        return key[1].rsplit("#", 1)[-1] if "w3.org/ns/shacl#" in key[1] else key[1]
    return str(key)


def _fmt(key: tuple) -> list[str]:
    return [_short(part) for part in key]


def _turtle(graph: Any) -> str | None:
    size = _triple_count(graph)
    if size is None or size > MAX_SNIPPET_TRIPLES:
        return None
    try:
        text = graph.serialize(format="turtle")
        return text.decode() if isinstance(text, bytes) else text
    except Exception:
        try:
            return "\n".join(
                " ".join(str(t) for t in tr) for tr in graph.triples((None, None, None))
            )
        except Exception:
            return None


def _term_key(graph: Any, term: Any) -> Any:
    """comparison.term_key, plus triple terms fingerprinted by their components (str() of a TripleTerm depends on the
    namespace manager of the graph it came from)."""
    from rdflib import BNode, Literal
    from starlayer.graph.model.triple import TripleTerm

    if term is None:
        return None
    if isinstance(term, TripleTerm):
        return (
            "TRIPLETERM",
            _term_key(graph, term.subject),
            _term_key(graph, term.predicate),
            _term_key(graph, term.object),
        )
    if isinstance(term, BNode):
        return (
            "BNODE",
            tuple(
                sorted(
                    (str(p), _term_key(graph, o))
                    for p, o in graph.predicate_objects(term)
                )
            ),
        )
    if isinstance(term, Literal):
        return (
            "LITERAL",
            str(term),
            str(term.datatype) if term.datatype else None,
            term.language,
        )
    return ("URI", str(term))


def _fingerprint(report_graph: Any) -> tuple[bool, Counter]:
    from tests.shacl.w3c_shacl12.comparison import conforms_of, find_report_node
    from tests.shacl.w3c_shacl12.namespaces import SH

    node = find_report_node(report_graph)
    counter: Counter = Counter()
    for result_node in report_graph.objects(node, SH.result):
        parts = [
            next(report_graph.objects(result_node, predicate), None)
            for predicate in (
                SH.focusNode,
                SH.resultPath,
                SH.sourceConstraintComponent,
                SH.value,
                SH.resultSeverity,
            )
        ]
        counter[tuple(_term_key(report_graph, part) for part in parts)] += 1
    return conforms_of(report_graph, node), counter


def _run_engine(data: Any, shapes: Any, options: dict[str, Any]) -> Any:
    from starlayer.shacl_engine.api import validate as new_validate

    rules = None if options.get("advanced", True) else False
    passed = {k: options[k] for k in _ENGINE_OPTIONS if options.get(k) not in (None, False, ())}
    if options.get("inference") in ("none", "None"):
        passed.pop("inference", None)

    def on_alarm(signum: int, frame: Any) -> None:
        raise _Timeout

    armed = False
    try:
        signal.signal(signal.SIGALRM, on_alarm)
        signal.setitimer(signal.ITIMER_REAL, ENGINE_TIMEOUT_S)
        armed = True
    except (ValueError, AttributeError):
        pass  # not the main thread: run without a time box
    try:
        try:
            return new_validate(
                data, shapes, conformance_disallows=_disallows(options), rules=rules, **passed
            )
        except AssertionError as exc:
            if "must be an rdflib term" not in str(exc):
                raise
            # The engine's report builder uses a plain rdflib Graph, which cannot hold a triple term (an engine bug,
            # recorded as such). Retry with a StarLayerGraph report so the comparison can still run.
            from starlayer.graph.graph.starlayer_graph import StarLayerGraph
            from starlayer.shacl_engine import report as engine_report

            saved = engine_report.Graph
            engine_report.Graph = StarLayerGraph
            try:
                outcome = new_validate(
                    data, shapes, conformance_disallows=_disallows(options), rules=rules, **passed
                )
            finally:
                engine_report.Graph = saved
            _state["report_patched"] = True
            return outcome
    finally:
        if armed:
            signal.setitimer(signal.ITIMER_REAL, 0)


def _compare(
    kind: str,
    old_call: Any,
    data: Any,
    shapes: Any,
    options: dict[str, Any],
    skip: list[str],
) -> Any:
    """Run ``old_call`` (always, unchanged) and, unless skipped, the new engine on snapshots taken first."""
    test = _current_test()
    base = {"test": test, "kind": kind}
    snap_data = snap_shapes = None
    if not skip:
        try:
            snap_data = _snapshot(data)
            snap_shapes = _snapshot(shapes) if shapes is not None else None
        except Exception as exc:
            skip = [f"snapshot_failed:{type(exc).__name__}"]

    _state["depth"] += 1
    try:
        try:
            old = old_call()
        except BaseException as exc:
            record = {
                **base,
                "outcome": "old_error",
                "error": f"{type(exc).__name__}: {str(exc)[:400]}",
            }
            if skip:
                record["skip_options"] = skip
            else:
                try:
                    record["engine_on_old_error"] = (
                        f"returned conforms={_run_engine(snap_data, snap_shapes, options).conforms}"
                    )
                except _Timeout:
                    record["engine_on_old_error"] = "timeout"
                except Exception as engine_exc:
                    record["engine_on_old_error"] = (
                        f"raised {type(engine_exc).__name__}: {str(engine_exc)[:200]}"
                    )
            _write(record)
            raise
    finally:
        _state["depth"] -= 1

    try:
        if skip:
            _write({**base, "outcome": "skipped", "skip_options": skip})
            return old
        started = time.time()
        before = (
            _triple_count(snap_data),
            _triple_count(snap_shapes) if snap_shapes is not None else None,
        )
        try:
            new = _run_engine(snap_data, snap_shapes, options)
        except _Timeout:
            _write(
                {
                    **base,
                    "outcome": "engine_error",
                    "error": f"timeout after {ENGINE_TIMEOUT_S}s",
                }
            )
            return old
        except Exception as exc:
            tb = traceback.extract_tb(exc.__traceback__)[-1]
            _write(
                {
                    **base,
                    "outcome": "engine_error",
                    "error": f"{type(exc).__name__}: {str(exc)[:400]}",
                    "where": f"{Path(tb.filename).name}:{tb.lineno}",
                }
            )
            return old
        elapsed = round(time.time() - started, 3)
        patched = _state.pop("report_patched", False)
        after = (
            _triple_count(snap_data),
            _triple_count(snap_shapes) if snap_shapes is not None else None,
        )
        mutated = before != after
        try:
            old_conforms, old_set = _fingerprint(old.report_graph)
            new_conforms, new_set = _fingerprint(new.report_graph)
        except Exception as exc:
            _write(
                {
                    **base,
                    "outcome": "engine_error",
                    "error": f"compare failed: {type(exc).__name__}: {exc}"[:400],
                }
            )
            return old
        only_old = list((old_set - new_set).elements())
        only_new = list((new_set - old_set).elements())
        if old_conforms == new_conforms and not only_old and not only_new:
            record = {
                **base,
                "outcome": "agree",
                "seconds": elapsed,
                "n_results": sum(old_set.values()),
            }
            if mutated:
                record["engine_mutated_input"] = True
            if patched:
                record["report_graph_patched"] = True
            _write(record)
        else:
            _write(
                {
                    **base,
                    "outcome": "differ",
                    "seconds": elapsed,
                    "engine_mutated_input": mutated,
                    "report_graph_patched": patched,
                    "details": {
                        "conforms_old": old_conforms,
                        "conforms_new": new_conforms,
                        "only_in_old": [_fmt(k) for k in only_old],
                        "only_in_new": [_fmt(k) for k in only_new],
                        "options": {
                            k: str(v)[:60] for k, v in options.items() if k in _IGNORED
                        },
                        "data_ttl": _turtle(snap_data),
                        "shapes_ttl": _turtle(
                            snap_shapes if snap_shapes is not None else snap_data
                        ),
                    },
                }
            )
    except Exception as exc:  # the harness itself must never alter a test
        _write(
            {
                **base,
                "outcome": "engine_error",
                "error": f"harness: {type(exc).__name__}: {exc}"[:400],
            }
        )
    return old


def _wrap_module_validate(original: Any) -> Any:
    signature = inspect.signature(original)

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if _state["depth"] > 0:
            return original(*args, **kwargs)
        try:
            bound = signature.bind_partial(*args, **kwargs)
            arguments = dict(bound.arguments)
            extra = arguments.pop("kwargs", {})
            data = arguments.pop("data_graph", None)
            shapes = arguments.pop("shacl_graph", None)
            ont = arguments.pop("ont_graph", None)
            custom_fn = arguments.get("validate_fn") is not None
            options = {**arguments, **extra}
            if ont is not None:
                options["ont_graph"] = ont
            skip = _skip_options(
                options, ont, custom_fn, options.get("shapes_graph_resource")
            )
        except Exception as exc:
            return _compare(
                "validate",
                lambda: original(*args, **kwargs),
                None,
                None,
                {},
                [f"harness:{exc}"[:80]],
            )
        return _compare(
            "validate", lambda: original(*args, **kwargs), data, shapes, options, skip
        )

    wrapper._differential_original = original  # type: ignore[attr-defined]
    return wrapper


def _wrap_schema_validate(original: Any, default_validate_fn: Any) -> Any:
    @functools.wraps(original)
    def wrapper(self: Any, data_graph: Any = None, **kwargs: Any) -> Any:
        if _state["depth"] > 0:
            return original(self, data_graph, **kwargs)
        try:
            sources = self._sources
            data = data_graph if data_graph is not None else sources.get("data_graph")
            shapes = sources.get("shacl_graph")
            options = dict(kwargs)
            if self.inference is not None and options.get("inference") is None:
                options["inference"] = self.inference
            custom_fn = self.validate_fn is not default_validate_fn
            if sources.get("ont_graph") is not None:
                options["ont_graph"] = sources["ont_graph"]
            skip = _skip_options(
                options,
                sources.get("ont_graph"),
                custom_fn,
                options.get("shapes_graph_resource"),
            )
            if data is None:
                skip.append("no_data_graph")
        except Exception as exc:
            return _compare(
                "schema.validate",
                lambda: original(self, data_graph, **kwargs),
                None,
                None,
                {},
                [f"harness:{exc}"[:80]],
            )
        return _compare(
            "schema.validate",
            lambda: original(self, data_graph, **kwargs),
            data,
            shapes,
            options,
            skip,
        )

    wrapper._differential_original = original  # type: ignore[attr-defined]
    return wrapper


def _wrap_depth_only(original: Any) -> Any:
    """apply_rules / evaluate / extract_subgraph call validate() internally; those inner calls are not compared."""

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _state["depth"] += 1
        try:
            return original(*args, **kwargs)
        finally:
            _state["depth"] -= 1

    return wrapper


def _install() -> None:
    import starlayer.shacl as shacl_pkg
    import starlayer.shacl.validator as validator

    if getattr(validator.validate, "_differential_original", None) is not None:
        return
    old_validate = validator.validate
    new_validate = _wrap_module_validate(old_validate)
    schema = validator.StarShaclSchema
    schema.validate = _wrap_schema_validate(
        schema.validate, validator._default_validate
    )  # type: ignore[method-assign]
    for name in ("apply_rules", "evaluate"):
        setattr(schema, name, _wrap_depth_only(getattr(schema, name)))
    replacements = {old_validate: new_validate}
    for name in ("apply_rules", "evaluate"):
        replacements[getattr(validator, name)] = _wrap_depth_only(
            getattr(validator, name)
        )
    extract = getattr(shacl_pkg, "extract_subgraph", None)
    if extract is not None:
        replacements[extract] = _wrap_depth_only(extract)
    for module in list(sys.modules.values()):
        if module is None or not getattr(module, "__name__", "").startswith(
            "starlayer"
        ):
            continue
        for attr, value in list(vars(module).items()):
            try:
                if value in replacements:
                    setattr(module, attr, replacements[value])
            except TypeError:
                continue


def pytest_configure(config: Any) -> None:
    path = _out_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _state["out"] = path.open("w", encoding="utf-8")
    _state["counts"] = Counter()
    _install()


def pytest_unconfigure(config: Any) -> None:
    out = _state.get("out")
    if out is not None:
        out.close()
        _state["out"] = None
    counts = _state["counts"]
    print(
        f"\n[differential] {sum(counts.values())} calls: {dict(counts)}",
        file=sys.stderr,
    )
