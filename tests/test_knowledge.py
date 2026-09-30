"""Server-side source provenance and stale-index checks, not yet executed."""
import pytest

from chem_agent.knowledge import KnowledgeIndex


def test_source_retrieval_empty_evidence_and_stale_index(tmp_path):
    knowledge = tmp_path / "knowledge-example"
    knowledge.mkdir()
    card = knowledge / "heat.md"
    card.write_text("# 显热\nsource: 自编\n\n单相恒比热无相变，热负荷等于质量流量乘比热乘温差。", encoding="utf-8")
    index = KnowledgeIndex.build(knowledge, tmp_path / "index")
    hits = index.search("单相恒比热")["hits"]
    assert hits and all(h["source"] == "自编" for h in hits)
    assert index.search("ZZZZZZ")["evidence_status"] == "insufficient"
    card.write_text(card.read_text(encoding="utf-8") + "\n修订资料", encoding="utf-8")
    with pytest.raises(ValueError, match="重新"):
        KnowledgeIndex.load(tmp_path / "index", knowledge)
