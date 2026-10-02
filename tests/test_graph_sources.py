"""Graph source traceability and knowledge-directory boundary checks."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chem_agent import cli
from chem_agent.config import Settings
from chem_agent.knowledge import KnowledgeBase
from chem_agent.retrieval import _map_result


def test_graph_source_ids_resolve_beyond_selected_hits(tmp_path: Path):
    cards = tmp_path / "data" / "knowledge"
    cards.mkdir(parents=True)
    (cards / "heat.md").write_text(
        "# 显热\n来源：教学卡；https://example.org/heat\n\n## 公式\nQ=m cp ΔT。",
        encoding="utf-8",
    )
    (cards / "units.md").write_text(
        "# 单位\n来源：BIPM；https://example.org/units\n\n## 单位\n1 kW = 1 kJ/s。",
        encoding="utf-8",
    )
    settings = Settings(root=tmp_path, api_key="sk-offline-secret")
    knowledge = KnowledgeBase(cards)
    directory = tmp_path / "build" / "lightrag" / "test"
    directory.mkdir(parents=True)
    (directory / "kv_store_text_chunks.json").write_text(
        json.dumps(
            {
                "chunk-hit": {"file_path": "heat.md", "content": "# 显热\nQ=m cp ΔT。"},
                "chunk-graph": {
                    "file_path": "units.md",
                    "content": "# 单位\n1 kW = 1 kJ/s。",
                },
            }
        ),
        encoding="utf-8",
    )
    raw = {
        "data": {
            "entities": [
                {
                    "entity_name": "显热",
                    "source_id": "chunk-hit<SEP>chunk-graph<SEP>chunk-missing",
                }
            ],
            "relationships": [
                {
                    "src_id": "显热",
                    "tgt_id": "功率",
                    "source_id": "chunk-graph",
                }
            ],
            "chunks": [
                {
                    "chunk_id": "chunk-hit",
                    "reference_id": "1",
                    "file_path": "heat.md",
                    "content": "# 显热\nQ=m cp ΔT。",
                }
            ],
            "references": [{"reference_id": "1", "file_path": "heat.md"}],
        }
    }
    result = _map_result(raw, "显热功率", 1, knowledge, settings, directory)
    retrieval = result["retrieval"]
    assert [hit["chunk_id"] for hit in result["hits"]] == ["chunk-hit"]
    assert [ref["chunk_id"] for ref in retrieval["references"]] == ["chunk-hit"]
    assert [source["chunk_id"] for source in retrieval["graph_sources"]] == [
        "chunk-hit",
        "chunk-graph",
    ]
    assert retrieval["graph_sources"][1]["url"] == "https://example.org/units"
    assert "1 kW" in retrieval["graph_sources"][1]["text"]
    assert "chunk-missing" in retrieval["entities"][0]["source_ids"]
    assert "chunk-missing" not in json.dumps(retrieval["graph_sources"])


def test_knowledge_base_rejects_symlinked_card_before_read(tmp_path: Path):
    cards = tmp_path / "cards"
    cards.mkdir()
    outside = tmp_path / "private.md"
    outside.write_text("PRIVATE", encoding="utf-8")
    (cards / "linked.md").symlink_to(outside)
    with pytest.raises(ValueError, match="符号链接"):
        KnowledgeBase(cards)


def test_cli_sanitizes_file_errors(monkeypatch, capsys, tmp_path: Path):
    def fail(_cls, _root):
        raise OSError(f"private path: {tmp_path / 'secret.md'}")

    monkeypatch.setattr(cli.Settings, "load", classmethod(fail))
    monkeypatch.setattr(sys, "argv", ["chem-agent", "doctor"])
    assert cli.main() == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "failed"
    assert str(tmp_path) not in output["error"]


def test_onnxruntime_import_does_not_create_telemetry_id_in_project(tmp_path: Path):
    environment = os.environ.copy()
    environment.pop("ORT_DISABLE_TELEMETRY", None)
    subprocess.run(
        [sys.executable, "-c", "import chem_agent.retrieval; import onnxruntime"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=True,
        timeout=30,
    )
    assert not (tmp_path / ":memory:.ses").exists()
