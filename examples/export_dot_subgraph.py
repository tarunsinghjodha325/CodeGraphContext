#!/usr/bin/env python3
"""
export_dot_subgraph.py
Export a small subgraph from the CodeGraphContext Neo4j DB to Graphviz DOT.

What it does:
- Connects to Neo4j (reads NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
- Finds nodes whose name contains a query (case-insensitive)
- Pulls nearby relationships (any direction) and emits a DOT graph
- Optionally writes to a .dot file, otherwise prints to stdout

Usage:
  python3 examples/export_dot_subgraph.py "requests.get" --limit 150 --out calls.dot

Env:
  NEO4J_URI (e.g. bolt://localhost:7687)
  NEO4J_USER (e.g. neo4j)
  NEO4J_PASSWORD

Requires:
  pip install neo4j

Note:
  This script is deliberately schema-agnostic. It matches any relationship types
  between matched nodes and their neighbors, so it should work even if the repo
  adds new relationship kinds (CALLS, IMPORTS, DEFINES, EXTENDS, etc.).
"""

import os
import sys
import argparse
from neo4j import GraphDatabase


def _get_env(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        print(f"Error: missing env var {name}", file=sys.stderr)
        sys.exit(2)
    return val


def _connect():
    uri = _get_env("NEO4J_URI", "bolt://localhost:7687")
    user = _get_env("NEO4J_USER", "neo4j")
    pwd = _get_env("NEO4J_PASSWORD")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    return driver


CYPHER = """
// 1) Find seed nodes by name substring (case-insensitive)
MATCH (seed)
WHERE toLower(seed.name) CONTAINS toLower($q)
WITH collect(seed) AS seeds
// 2) Expand one hop out (both directions) from seeds
UNWIND seeds AS s
MATCH (s)-[r]-(nbr)
WITH seeds + collect(distinct nbr) AS nodes, collect(distinct r) AS rels
// 3) Optional second hop to enrich context (comment out if too big)
WITH nodes, rels
UNWIND nodes AS n1
MATCH (n1)-[r2]-(n2)
WITH collect(distinct n1) + collect(distinct n2) AS allNodes, rels + collect(distinct r2) AS allRels
// 4) Limit to keep output manageable
WITH allNodes, allRels
LIMIT $limit
RETURN allNodes AS nodes, allRels AS rels
"""


def fetch_subgraph(driver, query: str, limit: int = 200):
    with driver.session() as sess:
        rec = sess.run(CYPHER, q=query, limit=limit).single()
        if not rec:
            return [], []
        return rec["nodes"], rec["rels"]


def _node_id(n) -> str:
    # Use Neo4j internal id or a stable composite; prefer explicit id if present
    # Many graphs include a 'id' or 'uid' property; fallback to element_id().
    if "id" in n:
        return str(n["id"])
    if "uid" in n:
        return str(n["uid"])
    return n.element_id  # neo4j >=5 returns a string element id


def _node_label(n) -> str:
    # Prefer 'name', else 'qualifiedName' or 'path', fall back to labels
    for k in ("name", "qualifiedName", "path", "symbol"):
        if k in n and n[k]:
            return str(n[k])
    # Fallback: labels + element id tail
    labels = ":".join(n.labels)
    return f"{labels} ({_node_id(n)[-6:]})"


def to_dot(nodes, rels) -> str:
    # Build a simple directed DOT; direction set by presence of start/end
    # For undirected relationships, we render as -- (Graphviz edge).
    # Here we’ll render all as ->, labeling with the relationship type.
    node_lines = []
    edge_lines = []
    seen_nodes = set()

    for n in nodes:
        nid = _node_id(n)
        if nid in seen_nodes:
            continue
        seen_nodes.add(nid)
        label = _node_label(n).replace('"', r'\"')
        # Color by label heuristic: Functions/Classes/Modules if labels exist
        color = "lightblue"
        if "Function" in n.labels:
            color = "lightgreen"
        elif "Class" in n.labels:
            color = "khaki"
        elif "Module" in n.labels or "File" in n.labels:
            color = "lightgray"

        node_lines.append(f'  "{nid}" [label="{label}", style=filled, fillcolor="{color}"];')

    for r in rels:
        # neo4j driver returns Relationship with start/end element ids
        start_id = r.start_node.element_id
        end_id = r.end_node.element_id
        typ = r.type
        edge_lines.append(f'  "{start_id}" -> "{end_id}" [label="{typ}"];')

    dot = ["digraph G {", '  rankdir=LR;', '  node [shape=box, fontname="Inter, Arial"];']
    dot.extend(node_lines)
    dot.extend(edge_lines)
    dot.append("}")
    return "\n".join(dot)


def main():
    ap = argparse.ArgumentParser(description="Export a DOT subgraph around a search term.")
    ap.add_argument("query", help="Name fragment to search (case-insensitive)")
    ap.add_argument("--limit", type=int, default=200, help="Max rows to fetch (default 200)")
    ap.add_argument("--out", type=str, default="", help="Write DOT output to file (default: stdout)")
    args = ap.parse_args()

    driver = _connect()
    try:
        nodes, rels = fetch_subgraph(driver, args.query, limit=args.limit)
    finally:
        driver.close()

    if not nodes:
        print("No matching nodes found for query:", args.query, file=sys.stderr)
        sys.exit(1)

    dot = to_dot(nodes, rels)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(dot)
        print(f"Wrote DOT to {args.out}")
    else:
        print(dot)


if __name__ == "__main__":
    main()
