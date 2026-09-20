#!/usr/bin/env python3
"""Task graph (DAG) — build, validate, topo-order, critical path."""
from __future__ import annotations

from typing import Any, Optional


def build_graph(nodes: list[dict], edges: Optional[list[dict]] = None) -> dict[str, Any]:
    norm_nodes = []
    for i, n in enumerate(nodes):
        nn = dict(n)
        nn["id"] = n.get("id") or f"node_{i}"
        nn["dependencies"] = list(n.get("dependencies") or [])
        nn["order_index"] = int(n.get("order_index", i))
        nn.setdefault("agent", n.get("assigned_agent") or "coder")
        nn.setdefault("estimated_runtime", float(n.get("estimated_runtime") or n.get("estimated_runtime_seconds") or 60))
        nn.setdefault("estimated_cost", float(n.get("estimated_cost") or 0.05))
        nn.setdefault("critical", n.get("critical", True))
        nn.setdefault("parallel_safe", bool(n.get("parallel_safe", False)))
        norm_nodes.append(nn)

    norm_edges = list(edges or [])
    if not norm_edges:
        for n in norm_nodes:
            for d in n["dependencies"]:
                norm_edges.append({"from": d, "to": n["id"], "type": "hard"})
    return {"nodes": norm_nodes, "edges": norm_edges}


def validate_graph(graph: dict) -> dict[str, Any]:
    nodes = {n["id"]: n for n in graph.get("nodes") or []}
    errors: list[str] = []
    for n in graph.get("nodes") or []:
        for d in n.get("dependencies") or []:
            if d not in nodes:
                errors.append(f"missing dependency {d} for {n['id']}")
    for e in graph.get("edges") or []:
        if e.get("from") not in nodes:
            errors.append(f"edge from unknown {e.get('from')}")
        if e.get("to") not in nodes:
            errors.append(f"edge to unknown {e.get('to')}")
    cycle = detect_cycle(graph)
    if cycle:
        errors.append("cycle detected: " + " -> ".join(cycle))
    return {"ok": not errors, "errors": errors, "node_count": len(nodes), "edge_count": len(graph.get("edges") or [])}


def detect_cycle(graph: dict) -> Optional[list[str]]:
    nodes = {n["id"]: n for n in graph.get("nodes") or []}
    adj: dict[str, list[str]] = {nid: [] for nid in nodes}
    for n in nodes.values():
        for d in n.get("dependencies") or []:
            if d in adj:
                adj[d].append(n["id"])
    for e in graph.get("edges") or []:
        frm, to = e.get("from"), e.get("to")
        if frm in adj and to and to not in adj[frm]:
            adj[frm].append(to)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in nodes}
    stack: list[str] = []

    def dfs(u: str) -> Optional[list[str]]:
        color[u] = GRAY
        stack.append(u)
        for v in adj.get(u, []):
            if color.get(v) == GRAY:
                return stack[stack.index(v):] + [v] if v in stack else [u, v, u]
            if color.get(v) == WHITE:
                cyc = dfs(v)
                if cyc:
                    return cyc
        stack.pop()
        color[u] = BLACK
        return None

    for nid in nodes:
        if color[nid] == WHITE:
            cyc = dfs(nid)
            if cyc:
                return cyc
    return None


def topological_order(graph: dict) -> list[str]:
    nodes = {n["id"]: n for n in graph.get("nodes") or []}
    indeg = {nid: 0 for nid in nodes}
    adj: dict[str, list[str]] = {nid: [] for nid in nodes}
    for n in nodes.values():
        for d in n.get("dependencies") or []:
            if d in adj:
                adj[d].append(n["id"])
                indeg[n["id"]] += 1
    for e in graph.get("edges") or []:
        frm, to = e.get("from"), e.get("to")
        if frm in adj and to in indeg and to not in adj[frm]:
            adj[frm].append(to)
            indeg[to] += 1

    ready = sorted([nid for nid, d in indeg.items() if d == 0],
                   key=lambda x: (nodes[x].get("order_index", 0), x))
    order: list[str] = []
    while ready:
        u = ready.pop(0)
        order.append(u)
        for v in adj.get(u, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.append(v)
                ready.sort(key=lambda x: (nodes[x].get("order_index", 0), x))
    if len(order) != len(nodes):
        raise ValueError("graph has cycle; cannot topo-sort")
    return order


def critical_path(graph: dict) -> dict[str, Any]:
    nodes = {n["id"]: n for n in graph.get("nodes") or []}
    if not nodes:
        return {"path": [], "seconds": 0}
    order = topological_order(graph)
    adj: dict[str, list[str]] = {nid: [] for nid in nodes}
    for n in nodes.values():
        for d in n.get("dependencies") or []:
            if d in adj:
                adj[d].append(n["id"])
    arrival = {nid: 0.0 for nid in nodes}
    pred = {nid: None for nid in nodes}
    dist = {}
    for u in order:
        dur = float(nodes[u].get("estimated_runtime") or 60)
        for v in adj.get(u, []):
            cand = arrival[u] + dur
            if cand > arrival[v]:
                arrival[v] = cand
                pred[v] = u
        dist[u] = arrival[u] + dur
    end = max(dist, key=lambda k: dist[k])
    path = []
    cur = end
    while cur:
        path.append(cur)
        cur = pred[cur]
    path.reverse()
    return {"path": path, "seconds": dist[end], "end": end}


def ordered_nodes(graph: dict) -> list[dict]:
    order = topological_order(graph)
    by_id = {n["id"]: n for n in graph.get("nodes") or []}
    return [by_id[i] for i in order]


# aliases
validate = validate_graph
build = build_graph
topo = topological_order
crit = critical_path
