# Graphify — query the codebase graph before reading files

A persistent knowledge graph of this repo lives at `graphify-out/graph.json`
(4,211 nodes / 10,254 edges / 200 communities, built from the code).

## When to use it

For ANY question about codebase structure, architecture, or relationships —
"how does X connect to Y", "what calls Z", "which files import W", "where is
the entry point" — query the graph BEFORE reading files or grepping.

## How (MCP tools — already connected in Cline)

- `query_graph`   — BFS traversal from a symbol name (returns nodes + edges with `file:line`)
- `shortest_path` — path between two symbols
- `get_node` / `get_neighbors` / `get_community` — focused lookups
- `god_nodes` / `graph_stats` — overview and most-connected hotspots

## How (CLI — works everywhere)

```bash
graphify query "TradeCenterService"            # pass a NODE NAME, not a sentence
graphify path "User" "Mailer" --undirected
graphify explain "register"
```

## Rules

- Pass a symbol / class / function name to queries — free-text questions return
  "No matching nodes".
- After editing files, refresh the graph: `graphify update .` (AST-only, no API cost).
- Every edge is tagged `EXTRACTED` / `INFERRED` / `AMBIGUOUS`. Cite `file:line`
  and state which tag a claim came from — do not present an inferred edge as fact.
