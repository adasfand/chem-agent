"""Read-only, attributable views of the validated LightRAG index.

Exploration never invokes a model, changes retrieval limits, or creates answer evidence.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

import networkx as nx

from chem_agent.retrieval import HybridRetriever


def _parts(value: Any) -> list[str]:
    return list(dict.fromkeys(part.strip() for part in str(value or "").split("<SEP>") if part))


def select_subgraph(graph: nx.Graph, query: str, limit: int) -> tuple[nx.Graph, list[str]]:
    """Select actual connected neighbors; every returned edge is an induced index edge."""
    ranked = sorted(graph, key=lambda node: (-graph.degree(node), str(node)))
    query = query.strip().casefold()
    matches = [node for node in ranked if query and query in str(node).casefold()]
    matches.sort(key=lambda node: (str(node).casefold() != query, -graph.degree(node), str(node)))
    if query and not matches:
        return graph.subgraph([]).copy(), []
    seeds = matches[: min(5, limit)] if query else ranked[: min(6, limit)]
    selected = set(seeds)
    # Favor neighbors connected to several visible entities, then high-degree hubs.
    while len(selected) < min(limit, len(graph)):
        frontier = {neighbor for node in selected for neighbor in graph.neighbors(node)} - selected
        if not frontier:
            if query:
                break
            frontier = set(ranked) - selected
        candidate = min(
            frontier,
            key=lambda node: (
                -len(set(graph.neighbors(node)) & selected),
                -graph.degree(node),
                str(node),
            ),
        )
        selected.add(candidate)
    # Stabilize ordering independently of GraphML insertion order.
    result = nx.Graph()
    result.add_nodes_from((node, graph.nodes[node]) for node in sorted(selected))
    result.add_edges_from(
        sorted(
            (min(a, b), max(a, b), data)
            for a, b, data in graph.edges(data=True)
            if a in selected and b in selected and a != b
        )
    )
    return result, seeds


def graph_overview(retriever: HybridRetriever, query: str = "", limit: int = 72) -> dict[str, Any]:
    """Expose whitelisted graph data only after normal index validity checks."""
    if not 12 <= limit <= 120 or len(query) > 100:
        raise ValueError("图谱范围应为 12–120 个实体，查询不超过 100 字。")
    status = retriever.index_status
    empty = {
        "state": status["state"],
        "message": status["message"],
        "scope": "index_exploration",
        "query": query.strip(),
        "entities": [],
        "relationships": [],
        "sources": [],
        "communities": [],
        "topics": [],
        "stats": {"total_entities": 0, "total_relationships": 0, "documents": 0},
    }
    if status["state"] != "ready":
        return empty
    try:
        graph = nx.read_graphml(retriever.directory / "graph_chunk_entity_relation.graphml")
        chunks = json.loads((retriever.directory / "kv_store_text_chunks.json").read_text("utf-8"))
    except (OSError, ValueError, nx.NetworkXException):
        return {**empty, "state": "error", "message": "图谱读取失败，请核对索引后重试。"}
    visible, seeds = select_subgraph(graph, query, limit)
    groups = (
        list(nx.community.greedy_modularity_communities(visible, weight=None))
        if visible.number_of_edges()
        else [{node} for node in visible]
    )
    groups.sort(key=lambda nodes: (-len(nodes), min(nodes)))
    community_of = {node: index for index, group in enumerate(groups) for node in group}
    communities = [
        {
            "id": index,
            "label": min(group, key=lambda node: (-visible.degree(node), node)),
            "size": len(group),
        }
        for index, group in enumerate(groups)
    ]
    entities = [
        {
            "id": node,
            "name": node,
            "type": str(data.get("entity_type", "")),
            "description": str(data.get("description", "")),
            "source_ids": _parts(data.get("source_id")),
            "degree": graph.degree(node),
            "visible_degree": visible.degree(node),
            "community": community_of[node],
            "seed": node in seeds,
        }
        for node, data in visible.nodes(data=True)
    ]
    relationships = [
        {
            "source": source,
            "target": target,
            "description": str(data.get("description", "")),
            "keywords": str(data.get("keywords", "")),
            "source_ids": _parts(data.get("source_id")),
        }
        for source, target, data in visible.edges(data=True)
    ]
    catalog = {item["doc_id"]: item for item in retriever.inventory()}
    sources = []
    ids = sorted({sid for item in [*entities, *relationships] for sid in item["source_ids"]})
    for chunk_id in ids:
        chunk = chunks.get(chunk_id, {})
        file_path = chunk.get("file_path") if isinstance(chunk, dict) else None
        if not isinstance(file_path, str) or not file_path:
            continue
        card = catalog.get(PurePosixPath(file_path).with_suffix("").as_posix())
        if not card or not isinstance(chunk.get("content"), str):
            continue
        sources.append(
            {
                "chunk_id": chunk_id,
                "doc_id": card["doc_id"],
                "title": card["title"],
                "source": card["source"],
                "text": chunk["content"],
            }
        )
    return {
        **empty,
        "message": "从有效索引抽取的真实子图；关系与来源可逐项核对。",
        "entities": entities,
        "relationships": relationships,
        "sources": sources,
        "communities": communities,
        "topics": sorted(graph, key=lambda node: (-graph.degree(node), node))[:12],
        "stats": {
            "total_entities": graph.number_of_nodes(),
            "total_relationships": graph.number_of_edges(),
            "documents": status["document_count"],
            "visible_entities": len(entities),
            "visible_relationships": len(relationships),
            "source_documents": len({source["doc_id"] for source in sources}),
            "truncated": len(visible) < len(graph),
        },
    }
