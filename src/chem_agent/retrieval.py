"""Persistent LightRAG retrieval with an explicit, offline lexical fallback."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath
from stat import S_IMODE
from typing import Any
from uuid import uuid4
from xml.etree.ElementTree import ParseError

from chem_agent.config import Settings
from chem_agent.knowledge import KnowledgeBase

# FastEmbed imports ONNX Runtime, whose default telemetry initialization can
# write a persistent :memory:.ses device identifier in the process cwd.
# Set this before the lazy FastEmbed import while honoring an explicit override.
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIM = 512
GRAPH_LANGUAGE = "Chinese"
_INDEX_CONFIG = "zh-v1"
_MANIFEST_SCHEMA = 2
_SOURCE_SEPARATOR = "<SEP>"
_CHUNK_TEXT_LIMIT = 1800
_DESCRIPTION_LIMIT = 360
_REQUIRED_STORE_FILES = (
    "graph_chunk_entity_relation.graphml",
    "kv_store_doc_status.json",
    "kv_store_text_chunks.json",
    "vdb_chunks.json",
    "vdb_entities.json",
    "vdb_relationships.json",
)
_RAG_STORAGES = (
    "full_docs",
    "text_chunks",
    "full_entities",
    "full_relations",
    "entity_chunks",
    "relation_chunks",
    "entities_vdb",
    "relationships_vdb",
    "chunks_vdb",
    "chunk_entity_relation_graph",
    "llm_response_cache",
    "doc_status",
)


def _index_root(settings: Settings) -> Path:
    return settings.root / "build" / "lightrag"


def _index_dir(settings: Settings, version: str) -> Path:
    return _index_root(settings) / f"{version[:16]}-{_INDEX_CONFIG}"


def _protect_index_tree(directory: Path) -> None:
    """Keep SDK cache and query prompts private, including files from earlier builds."""
    if directory.is_symlink() or directory.parent.is_symlink():
        raise ValueError("索引路径不能是符号链接。")
    if not directory.exists():
        return

    def protect(path: Path) -> None:
        if path.is_symlink():
            raise ValueError("索引不能包含符号链接。")
        expected = 0o700 if path.is_dir() else 0o600 if path.is_file() else None
        if expected is not None and S_IMODE(path.stat().st_mode) != expected:
            path.chmod(expected)

    protect(directory)
    for path in directory.rglob("*"):
        protect(path)


def _safe_index_directory(settings: Settings, directory: Path) -> bool:
    """Check cleanup cannot escape the project's literal index location."""
    try:
        expected = settings.root.resolve() / "build" / "lightrag"
        return not directory.is_symlink() and directory.resolve().parent == expected
    except (OSError, RuntimeError):
        return False


def _storage_signature(directory: Path) -> tuple[tuple[int, int, int, int, int], ...]:
    signature = []
    for name in _REQUIRED_STORE_FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing index storage")
        info = path.stat()
        if info.st_size <= 0:
            raise ValueError("empty index storage")
        signature.append(
            (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        )
    return tuple(signature)


def _validate_index_stores(
    directory: Path, documents: int, chunks: int, sources: list[str]
) -> None:
    """Parse stores once per file version; later status reads only stat metadata."""
    import networkx as nx
    import numpy as np

    if documents != len(sources) or len(set(sources)) != documents:
        raise ValueError("invalid document manifest")
    chunk_data = json.loads((directory / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
    doc_status = json.loads((directory / "kv_store_doc_status.json").read_text(encoding="utf-8"))
    if not isinstance(chunk_data, dict) or len(chunk_data) != chunks:
        raise ValueError("invalid chunk store")
    if (
        not isinstance(doc_status, dict)
        or len(doc_status) != documents
        or any(
            not isinstance(item, dict) or item.get("status") != "processed"
            for item in doc_status.values()
        )
    ):
        raise ValueError("invalid document status store")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("content"), str)
        or not item["content"].strip()
        or item.get("file_path") not in sources
        for item in chunk_data.values()
    ):
        raise ValueError("invalid chunk source")

    for name in ("chunks", "entities", "relationships"):
        vectors = json.loads((directory / f"vdb_{name}.json").read_text(encoding="utf-8"))
        if (
            not isinstance(vectors, dict)
            or vectors.get("embedding_dim") != EMBEDDING_DIM
            or not isinstance(vectors.get("data"), list)
            or not isinstance(vectors.get("matrix"), str)
        ):
            raise ValueError("invalid vector store")
        records = vectors["data"]
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("__id__"), str)
            or not item["__id__"]
            for item in records
        ):
            raise ValueError("invalid vector records")
        identifiers = {item["__id__"] for item in records}
        if len(identifiers) != len(records):
            raise ValueError("duplicate vector records")
        matrix = base64.b64decode(vectors["matrix"], validate=True)
        if len(matrix) != len(records) * EMBEDDING_DIM * np.dtype(np.float32).itemsize:
            raise ValueError("vector matrix does not match records")
        values = np.frombuffer(matrix, dtype=np.float32).reshape(-1, EMBEDDING_DIM)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            norms = np.linalg.norm(values, axis=1)
        if not np.isfinite(values).all() or not np.isfinite(norms).all() or (norms == 0).any():
            raise ValueError("invalid embedding values")
        if name == "chunks" and identifiers != set(chunk_data):
            raise ValueError("chunk vectors do not match source chunks")

    try:
        nx.read_graphml(directory / "graph_chunk_entity_relation.graphml")
    except (nx.NetworkXException, ParseError, KeyError, TypeError, ValueError):
        raise ValueError("invalid graph storage") from None


def _safe_string(value: Any, settings: Settings, limit: int) -> tuple[str, bool]:
    text = str(value or "")
    for private in (
        settings.api_key,
        str(settings.root.resolve()),
        str((settings.root / ".local").resolve()),
    ):
        if private:
            text = text.replace(private, "[已隐藏]")
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{10,}", "[已隐藏]", text)
    clipped = len(text) > limit
    return text[:limit], clipped


def _source_ids(value: Any) -> list[str]:
    values = value if isinstance(value, list) else str(value or "").split(_SOURCE_SEPARATOR)
    return [
        item
        for raw in values
        if (item := str(raw).strip()) and re.fullmatch(r"[A-Za-z0-9][\w.-]{0,127}", item)
    ][:24]


def _source_catalog(knowledge: KnowledgeBase) -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    for item in knowledge.inventory():
        doc_id = item["doc_id"]
        metadata = {"doc_id": doc_id, "title": item["title"], "source": item["source"]}
        catalog[item["file_path"]] = metadata
    return catalog


def _card_for_path(raw: Any, catalog: dict[str, dict[str, str]]) -> dict[str, str] | None:
    if not isinstance(raw, str) or not raw or _SOURCE_SEPARATOR in raw:
        return None
    normalized = raw.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        return None
    match = catalog.get(path.as_posix())
    if match is not None:
        return match
    # LightRAG may return a basename even if the inserted path was relative.
    matches = [item for name, item in catalog.items() if PurePosixPath(name).name == path.name]
    unique = {item["doc_id"]: item for item in matches}
    return next(iter(unique.values())) if len(unique) == 1 else None


def _source_url(source: str) -> str:
    match = re.search(r"https?://[^\s<>\"']+", source)
    return match.group(0).rstrip(".,;:!?)，。；：！？）]") if match else ""


def _bind_storage_workspace(rag: Any, directory: Path, *, building: bool) -> None:
    """Isolate SDK shared memory while retaining existing on-disk index paths.

    In the pinned LightRAG 1.5.7 file stores, construction fixes file paths;
    initialize_storages later binds shared data and locks by workspace. Bind
    before initialization, keeping all storage instances on the same namespace.
    The chunk-file snapshot also separates a rebuilt index at the same path.
    Never clear global SDK caches: another retriever may still be using them.
    """
    snapshot = directory / "kv_store_text_chunks.json"
    stamp = None
    if snapshot.is_file():
        info = snapshot.stat()
        stamp = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    identity = f"{directory.resolve()}\0{stamp}\0{uuid4().hex if building else ''}"
    workspace = "chem-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    rag.workspace = workspace
    for name in _RAG_STORAGES:
        storage = getattr(rag, name, None)
        if storage is not None:
            storage.workspace = workspace


def _make_rag(settings: Settings, directory: Path, *, allow_download: bool):
    """Construct the pinned SDK lazily, so offline fallback never loads a model."""
    _protect_index_tree(directory)
    import numpy as np
    from fastembed import TextEmbedding
    from lightrag import LightRAG
    from lightrag.llm.openai import openai_complete_if_cache
    from lightrag.utils import EmbeddingFunc

    cache = settings.root / ".local" / "fastembed"
    cache.mkdir(parents=True, exist_ok=True)
    embedder = TextEmbedding(
        model_name=EMBEDDING_MODEL,
        cache_dir=str(cache),
        local_files_only=not allow_download,
    )

    async def embed(texts: list[str]) -> np.ndarray:
        vectors = await asyncio.to_thread(lambda: list(embedder.embed(texts)))
        if not vectors:
            return np.empty((0, EMBEDDING_DIM), dtype=np.float32)
        return np.stack(vectors).astype(np.float32, copy=False)

    async def complete(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> str:
        if not settings.api_key:
            raise ValueError("尚未配置 DeepSeek 密钥。")
        # LightRAG supplies response_format for extraction. DeepSeek's JSON mode
        # works with non-thinking Chat Completions, so preserve that argument.
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        kwargs.setdefault("temperature", 0)
        kwargs.pop("timeout", None)
        return await openai_complete_if_cache(
            settings.model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=int(settings.request_timeout),
            **kwargs,
        )

    rag = LightRAG(
        working_dir=str(directory),
        workspace="",
        addon_params={"language": GRAPH_LANGUAGE},
        llm_model_func=complete,
        llm_model_name=settings.model,
        llm_model_max_async=2,
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBEDDING_DIM,
            max_token_size=512,
            model_name=EMBEDDING_MODEL,
            func=embed,
        ),
        embedding_func_max_async=2,
        entity_extract_max_gleaning=0,
        auto_manage_storages_states=False,
    )
    _bind_storage_workspace(rag, directory, building=allow_download)
    return rag


async def _query_ready(rag: Any, query: str, top_k: int) -> dict[str, Any]:
    from lightrag import QueryParam

    await rag.initialize_storages()
    try:
        return await rag.aquery_data(
            query,
            QueryParam(
                mode="mix",
                top_k=top_k,
                chunk_top_k=top_k,
                max_entity_tokens=900,
                max_relation_tokens=900,
                max_total_tokens=4500,
                enable_rerank=False,
            ),
        )
    finally:
        try:
            await rag.finalize_storages()
        finally:
            working_dir = getattr(rag, "working_dir", None)
            if isinstance(working_dir, (str, Path)):
                _protect_index_tree(Path(working_dir))


def _map_result(
    raw: dict[str, Any],
    query: str,
    top_k: int,
    knowledge: KnowledgeBase,
    settings: Settings,
    directory: Path,
) -> dict[str, Any]:
    catalog = _source_catalog(knowledge)
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    raw_metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    raw_keywords = raw_metadata.get("keywords")
    raw_keywords = raw_keywords if isinstance(raw_keywords, dict) else {}
    truncated = False

    def clipped(value: Any, limit: int = _DESCRIPTION_LIMIT) -> str:
        nonlocal truncated
        text, was_clipped = _safe_string(value, settings, limit)
        truncated |= was_clipped
        return text

    keywords: dict[str, list[str]] = {}
    for key in ("high_level", "low_level"):
        values = raw_keywords.get(key)
        values = values if isinstance(values, list) else []
        truncated |= len(values) > 8
        keywords[key] = [clipped(item, 80) for item in values[:8] if isinstance(item, str)]

    raw_entities = data.get("entities") if isinstance(data.get("entities"), list) else []
    raw_relationships = (
        data.get("relationships") if isinstance(data.get("relationships"), list) else []
    )
    raw_chunks = data.get("chunks") if isinstance(data.get("chunks"), list) else []
    raw_references = data.get("references") if isinstance(data.get("references"), list) else []
    truncated |= len(raw_entities) > 12 or len(raw_relationships) > 18 or len(raw_chunks) > top_k

    entities = []
    for item in raw_entities[:12]:
        if not isinstance(item, dict):
            continue
        name = clipped(item.get("entity_name"), 100)
        if name:
            entities.append(
                {
                    "id": name,
                    "name": name,
                    "type": clipped(item.get("entity_type"), 80),
                    "description": clipped(item.get("description")),
                    "source_ids": _source_ids(item.get("source_id")),
                }
            )

    relationships = []
    for item in raw_relationships[:18]:
        if not isinstance(item, dict):
            continue
        source = clipped(item.get("src_id"), 100)
        target = clipped(item.get("tgt_id"), 100)
        if not source or not target:
            continue
        description = clipped(item.get("description"))
        relation_id = hashlib.sha256(
            f"{source}\0{target}\0{description}".encode("utf-8")
        ).hexdigest()[:16]
        relationships.append(
            {
                "id": f"rel-{relation_id}",
                "source": source,
                "target": target,
                "description": description,
                "keywords": clipped(item.get("keywords"), 160),
                "source_ids": _source_ids(item.get("source_id")),
            }
        )

    refs_by_id = {
        str(item.get("reference_id")): item
        for item in raw_references
        if isinstance(item, dict) and item.get("reference_id")
    }
    chunks = []
    hits = []
    references = []
    seen_chunks = set()
    for item in raw_chunks:
        if len(chunks) >= top_k:
            break
        if not isinstance(item, dict):
            continue
        chunk_id = item.get("chunk_id")
        if not isinstance(chunk_id, str) or not re.fullmatch(r"[A-Za-z0-9][\w.-]{0,127}", chunk_id):
            continue
        if chunk_id in seen_chunks:
            continue
        reference_id = str(item.get("reference_id") or "")
        reference = refs_by_id.get(reference_id, {})
        card = _card_for_path(item.get("file_path") or reference.get("file_path"), catalog)
        if card is None:
            # A retrieved passage without a source cannot become a citation.
            continue
        text = clipped(item.get("content"), _CHUNK_TEXT_LIMIT)
        if not text.strip():
            continue
        seen_chunks.add(chunk_id)
        chunk = {
            "chunk_id": chunk_id,
            "title": card["title"],
            "text": text,
            "source": card["source"],
            "doc_id": card["doc_id"],
        }
        chunks.append(chunk)
        hits.append(dict(chunk))
        references.append(
            {
                "chunk_id": chunk_id,
                "source": card["source"],
                "url": _source_url(card["source"]),
                "reference_id": reference_id,
            }
        )

    # An entity can cite a source chunk that was not selected among top_k
    # retrieval hits. Resolve those real SDK chunk IDs from its persisted chunk
    # store rather than silently implying that the visible hits support every
    # graph edge. This is read-only and never promotes graph sources to hits.
    graph_ids = list(
        dict.fromkeys(
            source_id for item in [*entities, *relationships] for source_id in item["source_ids"]
        )
    )
    truncated |= len(graph_ids) > 32
    try:
        stored_chunks = json.loads((directory / "kv_store_text_chunks.json").read_text("utf-8"))
    except (OSError, ValueError):
        stored_chunks = {}
    if not isinstance(stored_chunks, dict):
        stored_chunks = {}
    hit_by_id = {hit["chunk_id"]: hit for hit in hits}
    graph_sources = []
    for chunk_id in graph_ids[:32]:
        hit = hit_by_id.get(chunk_id)
        if hit is not None:
            card = hit
            content = hit["text"]
        else:
            stored = stored_chunks.get(chunk_id)
            if not isinstance(stored, dict):
                continue
            card = _card_for_path(stored.get("file_path"), catalog)
            content = stored.get("content")
        if card is None or not isinstance(content, str) or not content.strip():
            continue
        graph_sources.append(
            {
                "chunk_id": chunk_id,
                "doc_id": card["doc_id"],
                "title": clipped(card["title"], 160),
                "source": clipped(card["source"], 500),
                "url": _source_url(card["source"]),
                "text": clipped(content, _CHUNK_TEXT_LIMIT),
            }
        )

    processing = raw_metadata.get("processing_info")
    processing = processing if isinstance(processing, dict) else {}
    public_processing = {
        key: value
        for key, value in processing.items()
        if key
        in {
            "total_entities_found",
            "total_relations_found",
            "entities_after_truncation",
            "relations_after_truncation",
            "merged_chunks_count",
            "final_chunks_count",
        }
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    }
    retrieval = {
        "query": query,
        "mode": "mix",
        "keywords": keywords,
        "entities": entities,
        "relationships": relationships,
        "chunks": chunks,
        "references": references,
        "graph_sources": graph_sources,
        "metadata": {
            "backend": "lightrag",
            "keyword_model": settings.model,
            "keyword_step": "LightRAG 内部关键词抽取（可能命中缓存）",
            "processing_info": public_processing,
            "returned_counts": {
                "entities": len(entities),
                "relationships": len(relationships),
                "chunks": len(chunks),
                "graph_sources": len(graph_sources),
            },
            "original_counts": {
                "entities": len(raw_entities),
                "relationships": len(raw_relationships),
                "chunks": len(raw_chunks),
            },
            "truncated": truncated,
        },
    }
    return {
        "query": query,
        "hits": hits,
        "status": "ok" if hits else "no_evidence",
        "retrieval": retrieval,
    }


class HybridRetriever:
    """Use a matching LightRAG index; otherwise return an explicit lexical result."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.lexical = KnowledgeBase(settings.knowledge_dir)
        self.version = self.lexical.version
        self.directory = _index_dir(settings, self.version)
        self._verified_signature: tuple[Any, ...] | None = None

    def inventory(self) -> list[dict[str, Any]]:
        return self.lexical.inventory()

    @property
    def index_status(self) -> dict[str, Any]:
        path = self.directory / "manifest.json"
        base: dict[str, Any] = {
            "state": "missing",
            "message": "尚未构建 LightRAG 索引，当前使用词法检索。",
            "document_count": 0,
            "chunk_count": 0,
            "backend": "lexical",
        }
        try:
            _protect_index_tree(_index_root(self.settings))
        except (OSError, ValueError):
            base.update(state="error", message="LightRAG 索引权限异常，当前使用词法检索。")
            return base
        if not path.is_file():
            # A knowledge edit changes the content-addressed directory. Detect
            # an earlier complete build so the UI can say "stale" rather than
            # incorrectly suggesting no index was ever built.
            for older in (self.settings.root / "build" / "lightrag").glob("*/manifest.json"):
                if older.parent == self.directory:
                    continue
                try:
                    manifest = json.loads(older.read_text(encoding="utf-8"))
                    documents = manifest.get("document_count")
                    chunks = manifest.get("chunk_count")
                    if (
                        manifest.get("schema_version") in {1, _MANIFEST_SCHEMA}
                        and isinstance(manifest.get("knowledge_version"), str)
                        and isinstance(documents, int)
                        and not isinstance(documents, bool)
                        and isinstance(chunks, int)
                        and not isinstance(chunks, bool)
                        and chunks > 0
                        and (older.parent / "kv_store_text_chunks.json").is_file()
                    ):
                        base.update(
                            state="stale",
                            message="已有旧版索引或知识资料已变化，请重建中文图谱；当前使用词法检索。",
                            document_count=documents,
                            chunk_count=chunks,
                        )
                        return base
                except (OSError, ValueError, TypeError, AttributeError):
                    continue
            return base
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("invalid manifest")
            documents = manifest.get("document_count")
            chunks = manifest.get("chunk_count")
            if any(
                isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (documents, chunks)
            ):
                raise ValueError("invalid counts")
            base.update(document_count=documents, chunk_count=chunks)
            if (
                manifest.get("schema_version") != _MANIFEST_SCHEMA
                or manifest.get("knowledge_version") != self.version
                or manifest.get("embedding_model") != EMBEDDING_MODEL
                or manifest.get("embedding_dim") != EMBEDDING_DIM
                or manifest.get("graph_language") != GRAPH_LANGUAGE
                or manifest.get("index_config") != _INDEX_CONFIG
            ):
                base.update(state="stale", message="知识或索引配置已变化，当前使用词法检索。")
                return base
            sources = manifest.get("source_files")
            if (
                not documents
                or not chunks
                or not isinstance(sources, list)
                or any(not isinstance(source, str) or not source for source in sources)
            ):
                raise ValueError("invalid source manifest")
            signature = (_storage_signature(self.directory), documents, chunks, tuple(sources))
            if signature != self._verified_signature:
                _validate_index_stores(self.directory, documents, chunks, sources)
                self._verified_signature = signature
        except (OSError, ValueError, TypeError, AttributeError):
            self._verified_signature = None
            base.update(state="error", message="LightRAG 索引不完整或损坏，当前使用词法检索。")
            return base
        base.update(state="ready", message="LightRAG 索引已就绪。", backend="lightrag")
        return base

    def _lexical(self, query: str, top_k: int, reason: str) -> dict[str, Any]:
        result = self.lexical.search(query, top_k)
        chunks = [
            {
                "chunk_id": hit["chunk_id"],
                "title": hit["title"],
                "text": hit["text"],
                "source": hit["source"],
                "doc_id": hit["doc_id"],
            }
            for hit in result["hits"]
        ]
        result["retrieval"] = {
            "query": query,
            "mode": "lexical",
            "keywords": {"high_level": [], "low_level": []},
            "entities": [],
            "relationships": [],
            "chunks": chunks,
            "references": [
                {
                    "chunk_id": hit["chunk_id"],
                    "source": hit["source"],
                    "url": _source_url(hit["source"]),
                }
                for hit in result["hits"]
            ],
            "graph_sources": [],
            "metadata": {"backend": "lexical", "fallback_reason": reason, "truncated": False},
        }
        return result

    def search(self, query: str, top_k: int = 3) -> dict[str, Any]:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 10:
            raise ValueError("top_k 必须是 1 至 10 的整数")
        if not isinstance(query, str):
            raise TypeError("query 必须是字符串")
        status = self.index_status
        if status["state"] != "ready" or not query.strip():
            return self._lexical(query, top_k, status["state"])
        try:
            rag = _make_rag(self.settings, self.directory, allow_download=False)
            raw = asyncio.run(_query_ready(rag, query, top_k))
            if not isinstance(raw, dict):
                raise ValueError("invalid retrieval result")
            return _map_result(raw, query, top_k, self.lexical, self.settings, self.directory)
        except Exception:
            # Provider exceptions can contain credentials, requests and local paths.
            raise ValueError("LightRAG 检索失败，请检查模型服务与本地索引。") from None


def _source_documents(knowledge: KnowledgeBase) -> tuple[list[str], list[str], list[str]]:
    root = knowledge.directory.resolve()
    known = {item["doc_id"] for item in knowledge.inventory()}
    texts: list[str] = []
    identifiers: list[str] = []
    relative_paths: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("知识目录包含不受支持的链接文件。")
        relative = path.relative_to(root).as_posix()
        doc_id = path.relative_to(root).with_suffix("").as_posix()
        if doc_id not in known:
            continue
        content = path.read_text(encoding="utf-8-sig")
        if not content.strip():
            continue
        texts.append(content)
        identifiers.append("doc-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24])
        relative_paths.append(relative)
    return texts, identifiers, relative_paths


async def _build(rag: Any, texts: list[str], identifiers: list[str], paths: list[str]) -> None:
    await rag.initialize_storages()
    try:
        track_id = await rag.ainsert(texts, ids=identifiers, file_paths=paths)
        statuses = await rag.aget_docs_by_track_id(track_id)
        if len(statuses) != len(texts) or any(
            getattr(getattr(item, "status", None), "value", getattr(item, "status", None))
            != "processed"
            for item in statuses.values()
        ):
            raise ValueError("部分知识文档构建失败。")
    finally:
        try:
            await rag.finalize_storages()
        finally:
            working_dir = getattr(rag, "working_dir", None)
            if isinstance(working_dir, (str, Path)):
                _protect_index_tree(Path(working_dir))


def build_index(settings: Settings) -> dict[str, Any]:
    """Explicitly build an index; this is the only path allowed to fetch the embedding model."""
    if not settings.api_key:
        raise ValueError("尚未配置 DeepSeek 密钥，无法构建 LightRAG 索引。")
    knowledge = KnowledgeBase(settings.knowledge_dir)
    retriever = HybridRetriever(settings)
    if retriever.index_status["state"] == "ready":
        return retriever.index_status
    directory = _index_dir(settings, knowledge.version)
    index_root = _index_root(settings)
    try:
        texts, identifiers, paths = _source_documents(knowledge)
        if not texts:
            raise ValueError("知识目录没有可索引的文档。")
        index_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        _protect_index_tree(index_root)
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(mode=0o700)
        rag = _make_rag(settings, directory, allow_download=True)
        asyncio.run(_build(rag, texts, identifiers, paths))
        chunk_store = directory / "kv_store_text_chunks.json"
        chunks = json.loads(chunk_store.read_text(encoding="utf-8"))
        if not isinstance(chunks, dict) or not chunks:
            raise ValueError("没有生成可检索片段。")
        manifest = {
            "schema_version": _MANIFEST_SCHEMA,
            "knowledge_version": knowledge.version,
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EMBEDDING_DIM,
            "graph_language": GRAPH_LANGUAGE,
            "index_config": _INDEX_CONFIG,
            "llm_model": settings.model,
            "document_count": len(texts),
            "chunk_count": len(chunks),
            "source_files": paths,
        }
        temporary = directory / "manifest.tmp"
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(directory / "manifest.json")
        _protect_index_tree(index_root)
    except Exception:
        # No manifest means the partial index can never be used for queries.
        if _safe_index_directory(settings, directory) and directory.is_dir():
            (directory / "manifest.json").unlink(missing_ok=True)
        try:
            _protect_index_tree(index_root)
        except (OSError, ValueError):
            pass
        raise ValueError("LightRAG 索引构建失败，请检查模型服务与知识文档。") from None
    return HybridRetriever(settings).index_status
