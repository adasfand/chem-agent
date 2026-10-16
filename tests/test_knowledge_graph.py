"""Index exploration must remain bounded, attributable and separate from answer evidence."""

import json
from types import SimpleNamespace

import networkx as nx
import pytest

from chem_agent.knowledge_graph import graph_overview, select_subgraph


@pytest.fixture
def graph():
    graph = nx.Graph()
    for index in range(30):
        graph.add_node(
            f"实体{index:02}",
            entity_type="concept",
            description=f"真实描述{index}",
            source_id="chunk-a<SEP>unresolved",
            private_field="never publish",
        )
    for index in range(1, 30):
        graph.add_edge("实体00", f"实体{index:02}", description=f"关系{index}", source_id="chunk-a")
    for index in range(1, 25):
        graph.add_edge(f"实体{index:02}", f"实体{index + 1:02}", source_id="chunk-b")
    graph.add_node("孤立主题", entity_type="material")
    return graph


@pytest.fixture
def retriever(tmp_path, graph):
    nx.write_graphml(graph, tmp_path / "graph_chunk_entity_relation.graphml")
    (tmp_path / "kv_store_text_chunks.json").write_text(
        json.dumps(
            {
                "chunk-a": {"content": "知识原文", "file_path": "a.md"},
                "chunk-b": {"content": "未知来源不发布", "file_path": "unknown.md"},
            }
        ),
        encoding="utf-8",
    )
    return SimpleNamespace(
        directory=tmp_path,
        index_status={"state": "ready", "message": "ready", "document_count": 1},
        inventory=lambda: [{"doc_id": "a", "title": "知识卡 A", "source": "教学来源"}],
    )


def test_bounded_deterministic_induced_subgraph(graph):
    selected, seeds = select_subgraph(graph, "", 12)
    assert len(selected) == 12
    assert len(seeds) == 6
    assert selected.number_of_edges() > len(selected)
    assert {frozenset(edge) for edge in selected.edges} == {
        frozenset(edge) for edge in graph.subgraph(selected).edges
    }
    reordered = nx.Graph()
    reordered.add_nodes_from(reversed(list(graph.nodes(data=True))))
    reordered.add_edges_from(reversed(list(graph.edges(data=True))))
    other, other_seeds = select_subgraph(reordered, "", 12)
    assert list(selected.nodes) == list(other.nodes)
    assert list(selected.edges) == list(other.edges)
    assert seeds == other_seeds


def test_unknown_and_isolated_query_never_padded_with_unrelated_entities(graph):
    missing, seeds = select_subgraph(graph, "不存在", 12)
    assert not missing and not seeds
    isolated, seeds = select_subgraph(graph, "孤立主题", 12)
    assert list(isolated) == seeds == ["孤立主题"]
    assert isolated.number_of_edges() == 0


def test_sources_resolved_without_becoming_retrieval_hits(retriever):
    result = graph_overview(retriever, limit=12)
    assert result["scope"] == "index_exploration"
    assert "hits" not in result and "citations" not in result
    assert result["stats"]["total_entities"] == 31
    assert result["stats"]["visible_entities"] == 12
    assert result["stats"]["truncated"]
    assert result["sources"] == [
        {
            "chunk_id": "chunk-a",
            "doc_id": "a",
            "title": "知识卡 A",
            "source": "教学来源",
            "text": "知识原文",
        }
    ]
    assert all(entity["source_ids"] == ["chunk-a", "unresolved"] for entity in result["entities"])
    assert "private_field" not in json.dumps(result)
    assert sum(group["size"] for group in result["communities"]) == 12


@pytest.mark.parametrize("state", ["missing", "stale", "error"])
def test_unready_indexes_not_presented_as_current(retriever, state):
    retriever.index_status["state"] = state
    result = graph_overview(retriever)
    assert result["state"] == state
    assert not result["entities"] and not result["relationships"]


def test_invalid_or_corrupt_requests_fail_safely(retriever):
    with pytest.raises(ValueError):
        graph_overview(retriever, limit=121)
    (retriever.directory / "kv_store_text_chunks.json").write_text("broken", encoding="utf-8")
    assert graph_overview(retriever)["state"] == "error"
