from __future__ import annotations

import argparse
import ast
import json
import tokenize
from collections import defaultdict
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, XSD

BASE = "https://github.com/hidden-graph/starlayer/kg/resource/"
ONTO = Namespace("https://github.com/hidden-graph/starlayer/kg/ontology#")
SCHEMA = Namespace("https://schema.org/")
PROV = Namespace("http://www.w3.org/ns/prov#")


@dataclass
class Scope:
    kind: str
    name: str
    lineno: int
    end_lineno: int
    uri: URIRef


def qpath(kind: str, value: str) -> URIRef:
    return URIRef(f"{BASE}{kind}/{quote(value, safe='')}" )


def module_name_from_path(path: Path, repo_root: Path) -> str:
    candidates = [
        (repo_root / "packages" / "graph" / "starlayergraph", "starlayergraph"),
        (repo_root / "packages" / "sparql" / "starsparql", "starsparql"),
        (repo_root / "packages" / "shacl" / "starshacl", "starshacl"),
    ]
    for base, root_mod in candidates:
        if base in path.parents or path == base:
            rel = path.relative_to(base)
            parts = [root_mod] + list(rel.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            return ".".join(parts)
    rel = path.relative_to(repo_root)
    return ".".join(rel.with_suffix("").parts)


def iter_python_files(repo_root: Path) -> Iterable[Path]:
    roots = [
        repo_root / "packages" / "graph" / "starlayergraph",
        repo_root / "packages" / "sparql" / "starsparql",
        repo_root / "packages" / "shacl" / "starshacl",
    ]
    for root in roots:
        for path in root.rglob("*.py"):
            yield path


def parse_comments(source: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for tok in tokenize.generate_tokens(StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            text = tok.string.lstrip("#").strip()
            if text:
                out.append((tok.start[0], text))
    return out


def node_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    pieces: list[str] = []
    args = node.args

    def ann(a: ast.arg) -> str:
        if a.annotation is None:
            return a.arg
        return f"{a.arg}: {ast.unparse(a.annotation)}"

    for a in args.posonlyargs:
        pieces.append(ann(a))
    if args.posonlyargs:
        pieces.append("/")
    for a in args.args:
        pieces.append(ann(a))
    if args.vararg is not None:
        pieces.append(f"*{ann(args.vararg)}")
    elif args.kwonlyargs:
        pieces.append("*")
    for a in args.kwonlyargs:
        pieces.append(ann(a))
    if args.kwarg is not None:
        pieces.append(f"**{ann(args.kwarg)}")
    ret = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(pieces)}){ret}"


def add_parameter_nodes(g: Graph, fn_uri: URIRef, fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    args = fn_node.args
    all_args: list[tuple[str, ast.arg, ast.expr | None]] = []

    def kind_name(prefix: str) -> str:
        return prefix

    defaults = [None] * (len(args.posonlyargs) + len(args.args) - len(args.defaults)) + list(args.defaults)

    for idx, a in enumerate(args.posonlyargs):
        all_args.append((kind_name("posonly"), a, defaults[idx]))
    offset = len(args.posonlyargs)
    for idx, a in enumerate(args.args):
        all_args.append((kind_name("positional"), a, defaults[offset + idx]))
    if args.vararg is not None:
        all_args.append((kind_name("vararg"), args.vararg, None))
    for idx, a in enumerate(args.kwonlyargs):
        d = args.kw_defaults[idx] if idx < len(args.kw_defaults) else None
        all_args.append((kind_name("kwonly"), a, d))
    if args.kwarg is not None:
        all_args.append((kind_name("varkw"), args.kwarg, None))

    for i, (k, a, d) in enumerate(all_args):
        p_uri = qpath("parameter", f"{fn_uri}::{a.arg}::{i}")
        g.add((p_uri, RDF.type, ONTO.Parameter))
        g.add((p_uri, RDFS.label, Literal(a.arg)))
        g.add((p_uri, ONTO.position, Literal(i, datatype=XSD.integer)))
        g.add((p_uri, ONTO.parameterKind, Literal(k)))
        if a.annotation is not None:
            g.add((p_uri, ONTO.annotation, Literal(ast.unparse(a.annotation))))
        if d is not None:
            g.add((p_uri, ONTO.defaultValue, Literal(ast.unparse(d))))
        g.add((fn_uri, ONTO.hasParameter, p_uri))

    return len(all_args)


def nearest_scope_uri(scopes: list[Scope], line: int) -> URIRef | None:
    candidates = [s for s in scopes if s.lineno <= line <= s.end_lineno]
    if not candidates:
        return None
    return sorted(candidates, key=lambda s: (s.end_lineno - s.lineno, s.lineno))[0].uri


def build_graph(repo_root: Path) -> tuple[Graph, dict[str, int], dict[tuple[str, str], int]]:
    g = Graph()
    g.bind("slkg", ONTO)
    g.bind("prov", PROV)
    g.bind("schema", SCHEMA)
    g.bind("dcterms", DCTERMS)
    g.bind("rdfs", RDFS)

    repo_uri = qpath("repository", "starlayer")
    g.add((repo_uri, RDF.type, ONTO.Repository))
    g.add((repo_uri, RDF.type, SCHEMA.SoftwareSourceCode))
    g.add((repo_uri, RDFS.label, Literal("starlayer")))
    g.add((repo_uri, SCHEMA.codeRepository, URIRef("https://github.com/hidden-graph/starlayer")))

    package_uris = {
        "starlayergraph": qpath("package", "starlayergraph"),
        "starsparql": qpath("package", "starsparql"),
        "starshacl": qpath("package", "starshacl"),
    }
    for pkg, uri in package_uris.items():
        g.add((uri, RDF.type, ONTO.Package))
        g.add((uri, RDFS.label, Literal(pkg)))
        g.add((repo_uri, ONTO.contains, uri))

    stats = defaultdict(int)
    pkg_deps: dict[tuple[str, str], int] = defaultdict(int)
    module_lookup: dict[str, URIRef] = {}

    python_files = list(iter_python_files(repo_root))
    known_modules = {module_name_from_path(path, repo_root) for path in python_files}

    for path in python_files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        comments = parse_comments(source)
        module_name = module_name_from_path(path, repo_root)
        module_uri = qpath("module", module_name)
        module_lookup[module_name] = module_uri

        package_name = module_name.split(".")[0]
        pkg_uri = package_uris.get(package_name)

        g.add((module_uri, RDF.type, ONTO.Module))
        g.add((module_uri, RDFS.label, Literal(module_name)))
        g.add((module_uri, ONTO.moduleName, Literal(module_name)))
        g.add((module_uri, ONTO.filePath, Literal(str(path.relative_to(repo_root)))))
        g.add((module_uri, DCTERMS.identifier, Literal(module_name)))
        if pkg_uri is not None:
            g.add((module_uri, ONTO.belongsToPackage, pkg_uri))
            g.add((pkg_uri, ONTO.contains, module_uri))

        mod_doc = ast.get_docstring(tree)
        if mod_doc:
            g.add((module_uri, RDFS.comment, Literal(mod_doc)))

        stats["modules"] += 1

        scopes: list[Scope] = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_qn = f"{module_name}.{node.name}"
                class_uri = qpath("class", class_qn)
                g.add((class_uri, RDF.type, ONTO.Class))
                g.add((class_uri, RDFS.label, Literal(node.name)))
                g.add((class_uri, ONTO.qualifiedName, Literal(class_qn)))
                g.add((class_uri, ONTO.lineStart, Literal(node.lineno, datatype=XSD.integer)))
                g.add((class_uri, ONTO.lineEnd, Literal(node.end_lineno or node.lineno, datatype=XSD.integer)))
                g.add((module_uri, ONTO.defines, class_uri))
                g.add((module_uri, ONTO.contains, class_uri))
                cdoc = ast.get_docstring(node)
                if cdoc:
                    g.add((class_uri, RDFS.comment, Literal(cdoc)))
                scopes.append(Scope("class", node.name, node.lineno, node.end_lineno or node.lineno, class_uri))
                stats["classes"] += 1

                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_qn = f"{class_qn}.{child.name}"
                        method_uri = qpath("method", method_qn)
                        g.add((method_uri, RDF.type, ONTO.Method))
                        g.add((method_uri, RDFS.label, Literal(child.name)))
                        g.add((method_uri, ONTO.qualifiedName, Literal(method_qn)))
                        g.add((method_uri, ONTO.signature, Literal(node_signature(child))))
                        g.add((method_uri, ONTO.lineStart, Literal(child.lineno, datatype=XSD.integer)))
                        g.add((method_uri, ONTO.lineEnd, Literal(child.end_lineno or child.lineno, datatype=XSD.integer)))
                        g.add((class_uri, ONTO.hasMethod, method_uri))
                        g.add((module_uri, ONTO.contains, method_uri))
                        mdoc = ast.get_docstring(child)
                        if mdoc:
                            g.add((method_uri, RDFS.comment, Literal(mdoc)))
                        add_parameter_nodes(g, method_uri, child)
                        scopes.append(
                            Scope("method", child.name, child.lineno, child.end_lineno or child.lineno, method_uri)
                        )
                        stats["methods"] += 1

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_qn = f"{module_name}.{node.name}"
                fn_uri = qpath("function", fn_qn)
                g.add((fn_uri, RDF.type, ONTO.Function))
                g.add((fn_uri, RDFS.label, Literal(node.name)))
                g.add((fn_uri, ONTO.qualifiedName, Literal(fn_qn)))
                g.add((fn_uri, ONTO.signature, Literal(node_signature(node))))
                g.add((fn_uri, ONTO.lineStart, Literal(node.lineno, datatype=XSD.integer)))
                g.add((fn_uri, ONTO.lineEnd, Literal(node.end_lineno or node.lineno, datatype=XSD.integer)))
                g.add((module_uri, ONTO.defines, fn_uri))
                g.add((module_uri, ONTO.contains, fn_uri))
                fdoc = ast.get_docstring(node)
                if fdoc:
                    g.add((fn_uri, RDFS.comment, Literal(fdoc)))
                add_parameter_nodes(g, fn_uri, node)
                scopes.append(Scope("function", node.name, node.lineno, node.end_lineno or node.lineno, fn_uri))
                stats["functions"] += 1

        for line, text in comments:
            target = nearest_scope_uri(scopes, line) or module_uri
            g.add((target, ONTO.commentText, Literal(text)))
            stats["comments"] += 1

        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for alias in n.names:
                    imported = alias.name
                    tgt_mod = imported
                    tgt_uri: URIRef
                    if imported.startswith(("starlayergraph", "starsparql", "starshacl")) and imported in known_modules:
                        tgt_uri = qpath("module", tgt_mod)
                        g.add((tgt_uri, RDF.type, ONTO.Module))
                        src_pkg = module_name.split(".")[0]
                        dst_pkg = imported.split(".")[0]
                        if src_pkg != dst_pkg:
                            pkg_deps[(src_pkg, dst_pkg)] += 1
                    else:
                        tgt_uri = qpath("external", tgt_mod)
                        g.add((tgt_uri, RDF.type, ONTO.ExternalModule))
                    g.add((module_uri, ONTO.importsModule, tgt_uri))
                    stats["imports"] += 1
            elif isinstance(n, ast.ImportFrom):
                mod = n.module or ""
                if n.level and mod:
                    parts = module_name.split(".")
                    base = parts[:-n.level]
                    mod = ".".join(base + [mod])
                elif n.level and not mod:
                    parts = module_name.split(".")
                    mod = ".".join(parts[:-n.level])

                if not mod:
                    continue

                if mod.startswith(("starlayergraph", "starsparql", "starshacl")) and mod in known_modules:
                    tgt_uri = qpath("module", mod)
                    g.add((tgt_uri, RDF.type, ONTO.Module))
                    src_pkg = module_name.split(".")[0]
                    dst_pkg = mod.split(".")[0]
                    if src_pkg != dst_pkg:
                        pkg_deps[(src_pkg, dst_pkg)] += 1
                else:
                    tgt_uri = qpath("external", mod)
                    g.add((tgt_uri, RDF.type, ONTO.ExternalModule))
                g.add((module_uri, ONTO.importsModule, tgt_uri))
                stats["imports"] += 1

    for (src, dst), _count in pkg_deps.items():
        src_uri = package_uris.get(src)
        dst_uri = package_uris.get(dst)
        if src_uri is not None and dst_uri is not None:
            g.add((src_uri, ONTO.dependsOnPackage, dst_uri))

    stats["triples"] = len(g)
    return g, dict(stats), pkg_deps


def write_dependency_mermaid(path: Path, pkg_deps: dict[tuple[str, str], int]) -> None:
    lines = ["graph LR"]
    seen = set()
    for (src, dst), count in sorted(pkg_deps.items()):
        edge = f"  {src} -->|{count}| {dst}"
        if edge not in seen:
            lines.append(edge)
            seen.add(edge)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a code knowledge graph for the StarLayer monorepo.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "kg")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    graph, stats, pkg_deps = build_graph(repo_root)

    ttl_path = out_dir / "codebase.ttl"
    graph.serialize(destination=str(ttl_path), format="turtle")

    summary = {
        "repository": "hidden-graph/starlayer",
        "generatedBy": "scripts/build_code_kg.py",
        "stats": stats,
        "packageDependencies": [
            {"from": src, "to": dst, "importEdges": count}
            for (src, dst), count in sorted(pkg_deps.items())
        ],
    }
    (out_dir / "codebase-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    write_dependency_mermaid(out_dir / "dependencies.mmd", pkg_deps)
    print(f"Wrote {ttl_path}")
    print(f"Triples: {stats['triples']}")


if __name__ == "__main__":
    main()
