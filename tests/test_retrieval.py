"""Offline contract tests for the persistent retrieval adapter."""

import json
from pathlib import Path
from stat import S_IMODE
from types import SimpleNamespace

import pytest

from chem_agent.config import Settings
from chem_agent.retrieval import HybridRetriever, _make_rag, _source_url, build_index


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    cards = tmp_path / "data" / "knowledge"
    cards.mkdir(parents=True)
    (cards / "heat.md").write_text(
        "# 显热热负荷\n"
        "来源：教学资料；https://example.org/heat，\n\n"
        "## 计算条件\n显热 Q = m × cp × ΔT，须明确比热和质量流量。\n",
        encoding="utf-8",
    )
    return Settings(root=tmp_path, api_key="sk-offline-secret")


def _write_stores(directory: Path, *, content: str, doc_id: str = "doc-heat") -> None:
    (directory / "kv_store_text_chunks.json").write_text(
        json.dumps({"chunk-heat": {"content": content, "file_path": "heat.md"}}),
        encoding="utf-8",
    )
    (directory / "kv_store_doc_status.json").write_text(
        json.dumps({doc_id: {"status": "processed"}}), encoding="utf-8"
    )
    (directory / "graph_chunk_entity_relation.graphml").write_text(
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"><graph edgedefault="undirected"/></graphml>',
        encoding="utf-8",
    )
    for name in ("chunks", "entities", "relationships"):
        (directory / f"vdb_{name}.json").write_text(
            json.dumps(
                {
                    "embedding_dim": 512,
                    "data": [{"__id__": "chunk-heat"}] if name == "chunks" else [],
                    "matrix": "",
                }
            ),
            encoding="utf-8",
        )


def _ready_manifest(retriever: HybridRetriever, *, version: str | None = None) -> None:
    retriever.directory.mkdir(parents=True, exist_ok=True)
    _write_stores(retriever.directory, content="显热公式")
    (retriever.directory / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "knowledge_version": version or retriever.version,
                "embedding_model": "BAAI/bge-small-zh-v1.5",
                "embedding_dim": 512,
                "graph_language": "Chinese",
                "index_config": "zh-v1",
                "document_count": 1,
                "chunk_count": 1,
                "source_files": ["heat.md"],
            }
        ),
        encoding="utf-8",
    )


def test_missing_index_uses_lexical_without_loading_model(settings, monkeypatch):
    def fail(*_args, **_kwargs):
        pytest.fail("unbuilt index must not construct LightRAG or download a model")

    monkeypatch.setattr("chem_agent.retrieval._make_rag", fail)
    retriever = HybridRetriever(settings)
    assert retriever.index_status == {
        "state": "missing",
        "message": "尚未构建 LightRAG 索引，当前使用词法检索。",
        "document_count": 0,
        "chunk_count": 0,
        "backend": "lexical",
    }
    result = retriever.search("显热热负荷公式")
    assert result["status"] == "ok"
    assert result["retrieval"]["mode"] == "lexical"
    assert result["retrieval"]["metadata"]["fallback_reason"] == "missing"
    assert result["hits"][0]["chunk_id"] == result["retrieval"]["chunks"][0]["chunk_id"]
    assert result["retrieval"]["references"][0]["url"] == "https://example.org/heat"


def test_stale_or_corrupt_manifest_falls_back_without_model(settings, monkeypatch):
    monkeypatch.setattr(
        "chem_agent.retrieval._make_rag",
        lambda *_a, **_k: pytest.fail("stale index must not load model"),
    )
    retriever = HybridRetriever(settings)
    _ready_manifest(retriever, version="older-knowledge-version")
    assert retriever.index_status["state"] == "stale"
    assert retriever.search("显热公式")["retrieval"]["mode"] == "lexical"
    manifest_path = retriever.directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["knowledge_version"] = retriever.version
    manifest.pop("graph_language")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert retriever.index_status["state"] == "stale"
    (retriever.directory / "manifest.json").write_text("{broken", encoding="utf-8")
    assert retriever.index_status["state"] == "error"
    assert retriever.search("显热公式")["retrieval"]["metadata"]["fallback_reason"] == "error"


def test_changed_cards_mark_previous_complete_index_stale(settings, monkeypatch):
    monkeypatch.setattr(
        "chem_agent.retrieval._make_rag",
        lambda *_a, **_k: pytest.fail("changed knowledge must use lexical search"),
    )
    previous = HybridRetriever(settings)
    _ready_manifest(previous)
    card = settings.knowledge_dir / "heat.md"
    card.write_text(card.read_text(encoding="utf-8") + "\n适用条件：无相变。", encoding="utf-8")
    current = HybridRetriever(settings)
    assert current.directory != previous.directory
    assert current.index_status["state"] == "stale"
    assert current.index_status["backend"] == "lexical"
    assert current.search("显热公式")["retrieval"]["mode"] == "lexical"


def test_old_english_index_remains_available_but_is_not_ready(settings, monkeypatch):
    retriever = HybridRetriever(settings)
    old_dir = settings.root / "build" / "lightrag" / retriever.version[:16]
    assert old_dir != retriever.directory
    old_dir.mkdir(parents=True)
    (old_dir / "kv_store_text_chunks.json").write_text(
        json.dumps({"old-chunk": {"content": "old graph"}}), encoding="utf-8"
    )
    (old_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "knowledge_version": retriever.version,
                "document_count": 1,
                "chunk_count": 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "chem_agent.retrieval._make_rag",
        lambda *_a, **_k: pytest.fail("English index must never be loaded"),
    )
    assert retriever.index_status["state"] == "stale"
    assert retriever.search("显热公式")["retrieval"]["mode"] == "lexical"
    assert (old_dir / "manifest.json").is_file()


def test_rag_passes_chinese_to_sdk_without_downloading(settings, monkeypatch):
    import fastembed
    import lightrag

    constructors = []

    def fake_embedding(**kwargs):
        constructors.append(("embedding", kwargs))
        return object()

    def fake_rag(**kwargs):
        constructors.append(("rag", kwargs))
        return object()

    monkeypatch.setattr(fastembed, "TextEmbedding", fake_embedding)
    monkeypatch.setattr(lightrag, "LightRAG", fake_rag)
    _make_rag(settings, settings.root / "index", allow_download=False)
    assert constructors[0][1]["local_files_only"] is True
    assert constructors[1][1]["addon_params"] == {"language": "Chinese"}


def test_ready_mix_maps_graph_and_real_chunks(settings, monkeypatch):
    retriever = HybridRetriever(settings)
    _ready_manifest(retriever)
    calls = []

    class FakeRAG:
        def __init__(self, directory):
            self.working_dir = str(directory)

        async def initialize_storages(self):
            calls.append("initialize")

        async def aquery_data(self, query, param):
            calls.append((query, param.mode, param.top_k, param.chunk_top_k))
            cache = Path(self.working_dir) / "kv_store_llm_response_cache.json"
            cache.write_text('{"keywords": {"original_prompt": "私有查询"}}', encoding="utf-8")
            cache.chmod(0o644)
            return {
                "status": "success",
                "data": {
                    "entities": [
                        {
                            "entity_name": "显热",
                            "entity_type": "概念",
                            "description": "由温度变化引起的热量",
                            "source_id": "chunk-heat<SEP>chunk-other",
                        }
                    ],
                    "relationships": [
                        {
                            "src_id": "显热",
                            "tgt_id": "比热",
                            "description": "计算需要比热",
                            "keywords": "显热,比热",
                            "source_id": "chunk-heat<SEP>chunk-other",
                        }
                    ],
                    "chunks": [
                        {
                            "chunk_id": "chunk-heat",
                            "reference_id": "1",
                            "file_path": "heat.md",
                            "content": "# 显热热负荷\n显热 Q = m × cp × ΔT。",
                        }
                    ],
                    "references": [{"reference_id": "1", "file_path": "heat.md"}],
                },
                "metadata": {
                    "query_mode": "mix",
                    "keywords": {"high_level": ["热量"], "low_level": ["显热", "比热"]},
                    "processing_info": {"final_chunks_count": 1},
                },
            }

        async def finalize_storages(self):
            calls.append("finalize")

    def make_rag(_settings, directory, *, allow_download):
        assert directory == retriever.directory
        assert allow_download is False
        return FakeRAG(directory)

    monkeypatch.setattr("chem_agent.retrieval._make_rag", make_rag)
    result = retriever.search("显热公式", top_k=2)
    assert result["status"] == "ok"
    assert result["hits"] == [
        {
            "chunk_id": "chunk-heat",
            "title": "显热热负荷",
            "text": "# 显热热负荷\n显热 Q = m × cp × ΔT。",
            "source": "教学资料；https://example.org/heat，",
            "doc_id": "heat",
        }
    ]
    assert "score" not in result["hits"][0]
    retrieval = result["retrieval"]
    assert retrieval["mode"] == "mix"
    assert retrieval["entities"][0]["source_ids"] == ["chunk-heat", "chunk-other"]
    assert retrieval["relationships"][0]["source"] == "显热"
    assert retrieval["references"][0]["url"] == "https://example.org/heat"
    assert retrieval["metadata"]["keyword_model"] == settings.model
    assert retrieval["metadata"]["keyword_step"].startswith("LightRAG")
    assert calls == ["initialize", ("显热公式", "mix", 2, 2), "finalize"]
    assert (
        S_IMODE((retriever.directory / "kv_store_llm_response_cache.json").stat().st_mode) == 0o600
    )
    assert settings.api_key not in json.dumps(result, ensure_ascii=False)
    assert str(settings.root) not in json.dumps(result, ensure_ascii=False)


def test_ready_query_failure_is_sanitized(settings, monkeypatch):
    retriever = HybridRetriever(settings)
    _ready_manifest(retriever)

    class FailingRAG:
        async def initialize_storages(self):
            pass

        async def aquery_data(self, _query, _param):
            raise RuntimeError(f"provider payload {settings.api_key} {settings.root}")

        async def finalize_storages(self):
            pass

    monkeypatch.setattr("chem_agent.retrieval._make_rag", lambda *_a, **_k: FailingRAG())
    with pytest.raises(ValueError) as error:
        retriever.search("显热公式")
    assert "LightRAG 检索失败" in str(error.value)
    assert settings.api_key not in str(error.value)
    assert str(settings.root) not in str(error.value)


def test_missing_or_corrupt_store_is_not_ready(settings):
    retriever = HybridRetriever(settings)
    _ready_manifest(retriever)
    assert retriever.index_status["state"] == "ready"
    (retriever.directory / "graph_chunk_entity_relation.graphml").unlink()
    assert retriever.index_status["state"] == "error"
    _write_stores(retriever.directory, content="显热公式")
    assert retriever.index_status["state"] == "ready"
    (retriever.directory / "vdb_chunks.json").write_text("{broken", encoding="utf-8")
    assert retriever.index_status["state"] == "error"


def test_index_status_repairs_existing_cache_permissions(settings):
    retriever = HybridRetriever(settings)
    _ready_manifest(retriever)
    cache = retriever.directory / "kv_store_llm_response_cache.json"
    cache.write_text('{"keywords": {"original_prompt": "私有查询"}}', encoding="utf-8")
    root = settings.root / "build" / "lightrag"
    root.chmod(0o755)
    retriever.directory.chmod(0o755)
    cache.chmod(0o644)
    assert retriever.index_status["state"] == "ready"
    assert S_IMODE(root.stat().st_mode) == 0o700
    assert S_IMODE(retriever.directory.stat().st_mode) == 0o700
    assert S_IMODE(cache.stat().st_mode) == 0o600
    assert all(S_IMODE(path.stat().st_mode) == 0o600 for path in retriever.directory.iterdir())


def test_index_directory_symlink_is_rejected_without_following_target(settings):
    retriever = HybridRetriever(settings)
    target = settings.root / "outside"
    target.mkdir()
    external_manifest = target / "manifest.json"
    external_manifest.write_text("external data", encoding="utf-8")
    retriever.directory.parent.mkdir(parents=True)
    retriever.directory.symlink_to(target, target_is_directory=True)
    assert retriever.index_status["state"] == "error"
    with pytest.raises(ValueError, match="LightRAG 索引构建失败"):
        build_index(settings)
    assert target.is_dir()
    assert external_manifest.read_text(encoding="utf-8") == "external data"


def test_build_is_explicit_and_publishes_manifest_last(settings, monkeypatch):
    created = []
    old_dir = settings.root / "build" / "lightrag" / HybridRetriever(settings).version[:16]
    old_dir.mkdir(parents=True)
    old_marker = old_dir / "old-index.marker"
    old_marker.write_text("preserved", encoding="utf-8")

    class FakeRAG:
        def __init__(self, directory):
            self.directory = directory
            self.ids = []

        async def initialize_storages(self):
            pass

        async def ainsert(self, texts, *, ids, file_paths):
            assert len(texts) == 1
            assert file_paths == ["heat.md"]
            assert all(not path.startswith("/") for path in file_paths)
            self.ids = ids
            _write_stores(self.directory, content=texts[0], doc_id=ids[0])
            (self.directory / "kv_store_llm_response_cache.json").write_text(
                '{"keywords": {"original_prompt": "私有查询"}}', encoding="utf-8"
            )
            assert not (self.directory / "manifest.json").exists()
            return "track-1"

        async def aget_docs_by_track_id(self, track_id):
            assert track_id == "track-1"
            return {key: SimpleNamespace(status="processed") for key in self.ids}

        async def finalize_storages(self):
            pass

    def make_rag(_settings, directory, *, allow_download):
        assert allow_download is True
        rag = FakeRAG(directory)
        created.append(rag)
        return rag

    monkeypatch.setattr("chem_agent.retrieval._make_rag", make_rag)
    status = build_index(settings)
    assert status["state"] == "ready"
    assert status["backend"] == "lightrag"
    assert status["document_count"] == status["chunk_count"] == 1
    manifest_text = (HybridRetriever(settings).directory / "manifest.json").read_text()
    assert settings.api_key not in manifest_text
    assert str(settings.root) not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["source_files"] == ["heat.md"]
    assert manifest["schema_version"] == 2
    assert manifest["graph_language"] == "Chinese"
    assert manifest["index_config"] == "zh-v1"
    assert old_marker.read_text(encoding="utf-8") == "preserved"
    assert S_IMODE(old_marker.stat().st_mode) == 0o600
    assert (
        S_IMODE(
            (HybridRetriever(settings).directory / "kv_store_llm_response_cache.json")
            .stat()
            .st_mode
        )
        == 0o600
    )
    assert build_index(settings)["state"] == "ready"
    assert len(created) == 1


def test_build_provider_failure_does_not_publish_ready_or_secret(settings, monkeypatch):
    class FailingRAG:
        async def initialize_storages(self):
            pass

        async def ainsert(self, *_args, **_kwargs):
            raise RuntimeError(f"provider failure {settings.api_key} {settings.root}")

        async def finalize_storages(self):
            pass

    monkeypatch.setattr("chem_agent.retrieval._make_rag", lambda *_a, **_k: FailingRAG())
    with pytest.raises(ValueError) as error:
        build_index(settings)
    assert settings.api_key not in str(error.value)
    assert str(settings.root) not in str(error.value)
    assert HybridRetriever(settings).index_status["state"] != "ready"


def test_source_url_extracts_embedded_link_and_removes_chinese_punctuation():
    assert _source_url("BIPM SI Brochure；https://www.bipm.org/en/publications/si-brochure。") == (
        "https://www.bipm.org/en/publications/si-brochure"
    )
