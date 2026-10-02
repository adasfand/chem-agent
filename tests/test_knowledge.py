from pathlib import Path

import pytest

from chem_agent.knowledge import KnowledgeBase


def test_colloquial_salt_concentration_query_recalls_basis_guidance():
    kb = KnowledgeBase(Path(__file__).resolve().parents[1] / "data" / "knowledge")
    result = kb.search("混合后的盐浓度怎么算")
    assert result["status"] == "ok"
    assert any("质量分数" in hit["text"] for hit in result["hits"])


KNOWLEDGE = Path(__file__).resolve().parents[1] / "data" / "knowledge"


@pytest.fixture(scope="module")
def knowledge() -> KnowledgeBase:
    return KnowledgeBase(KNOWLEDGE)


def test_inventory_has_attributed_original_cards(knowledge: KnowledgeBase) -> None:
    inventory = knowledge.inventory()
    assert len(inventory) == 15
    assert len({item["doc_id"] for item in inventory}) == 15
    assert all("项目自编教学说明，非实测物性数据" in item["source"] for item in inventory)
    assert all(item["chunk_count"] >= 1 for item in inventory)
    inventory[0]["title"] = "changed outside"
    assert knowledge.inventory()[0]["title"] != "changed outside"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("显热热负荷怎么计算", "01_sensible_heat"),
        ("加热器功率的公式是什么", "01_sensible_heat"),
        ("heat duty 计算公式", "01_sensible_heat"),
        ("1000 kg/h 换算为 kg/s", "03_mass_flow"),
        ("公斤每小时转每秒的质量流率", "03_mass_flow"),
        ("两股物流混合后的盐质量分数怎么计算", "10_mixing_balance"),
        ("混配后含盐率计算", "10_mixing_balance"),
        ("摄氏温差和开尔文温差", "04_temperature_difference"),
        ("升温发生蒸发时可以直接使用简化热负荷公式吗", "02_heat_assumptions"),
        ("没有给出比热容能计算吗", "06_specific_heat"),
    ],
)
def test_retrieval_with_paraphrases(knowledge: KnowledgeBase, query: str, expected: str) -> None:
    result = knowledge.search(query)
    assert result["status"] == "ok"
    assert expected in {hit["doc_id"] for hit in result["hits"]}
    for hit in result["hits"]:
        assert hit["chunk_id"].startswith(hit["doc_id"] + ":")
        assert hit["text"].startswith("# " + hit["title"])
        assert hit["source"]
        assert hit["score"] >= knowledge.min_score


@pytest.mark.parametrize(
    "query",
    [
        "",
        "  ",
        "明天北京天气怎么样",
        "推荐一部科幻电影",
        "股票交易策略",
        "如何计算股票收益",
        "今天的日程如何安排",
        "xqzvbnm",
    ],
)
def test_unrelated_queries_do_not_get_forced_hits(knowledge: KnowledgeBase, query: str) -> None:
    assert knowledge.search(query) == {
        "query": query,
        "hits": [],
        "status": "no_evidence",
    }


def test_top_k_and_invalid_limits(knowledge: KnowledgeBase) -> None:
    assert len(knowledge.search("质量流量", top_k=1)["hits"]) == 1
    for invalid in [0, -1, 11, 1.5, True, "3", None]:
        with pytest.raises(ValueError, match="top_k"):
            knowledge.search("热负荷", top_k=invalid)
    with pytest.raises(TypeError, match="query"):
        knowledge.search(None)


def test_files_rebuild_index_and_stable_section_ids(tmp_path: Path) -> None:
    card = tmp_path / "custom.md"
    card.write_text(
        "# 自定义热负荷\n来源：测试作者\n\n## 公式\n热负荷是加热功率。\n",
        encoding="utf-8",
    )
    initial = KnowledgeBase(tmp_path)
    initial_hit = initial.search("加热功率")["hits"][0]
    assert initial_hit["source"] == "测试作者"
    assert initial_hit["doc_id"] == "custom"
    assert initial.version == KnowledgeBase(tmp_path).version
    card.write_text(
        "# 自定义热负荷\n来源：测试作者\n\n## 新增\n仅为新段落。\n"
        "\n## 公式\n热负荷是加热功率，单位 kW。\n",
        encoding="utf-8",
    )
    refreshed = KnowledgeBase(tmp_path)
    refreshed_hit = refreshed.search("加热功率")["hits"][0]
    assert refreshed.version != initial.version
    assert refreshed_hit["chunk_id"] == initial_hit["chunk_id"]
    assert "单位 kW" in refreshed_hit["text"]
    assert refreshed.inventory()[0]["chunk_count"] == 2


def test_empty_directory_and_plain_text(tmp_path: Path) -> None:
    empty = KnowledgeBase(tmp_path)
    assert empty.inventory() == []
    assert empty.search("质量流量")["status"] == "no_evidence"
    (tmp_path / "flow.txt").write_text("质量流量使用 kg/s 单位。", encoding="utf-8")
    populated = KnowledgeBase(tmp_path)
    hit = populated.search("质量流量")["hits"][0]
    assert hit["title"] == "flow"
    assert hit["source"] == "来源未注明"
    assert populated.version != empty.version
