"""Rebuildable character TF-IDF retrieval; JSON snapshots, no pickle loading."""
import hashlib
import json
from pathlib import Path
import re

from sklearn.feature_extraction.text import TfidfVectorizer


def read_documents(directory: Path) -> list[dict]:
    documents = []
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8-sig")
        lines = raw.splitlines()
        # Knowledge cards declare source explicitly. Ordinary TXT remains supported.
        source = next((s.split(":", 1)[1].strip() for s in lines if s.startswith("source:")), "来源待核对")
        title = next((s.lstrip("# ") for s in lines if s.startswith("# ")), path.stem)
        documents.append({"doc_id": path.relative_to(directory).as_posix(),
                          "title": title, "source": source, "text": raw,
                          "sha256": hashlib.sha256(raw.encode()).hexdigest()})
    if not documents:
        raise ValueError(f"未找到 Markdown/TXT 知识资料：{directory}")
    return documents


def corpus_hash(documents: list[dict]) -> str:
    return hashlib.sha256(json.dumps(documents, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def split_documents(documents: list[dict]) -> list[dict]:
    chunks = []
    for doc in documents:
        section, number = doc["title"], 0
        for paragraph in re.split(r"\n\s*\n", doc["text"]):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if paragraph.startswith("#"):
                section = paragraph.splitlines()[0].lstrip("# ")
            # Headings/source records are metadata, not standalone evidence hits.
            paragraph = "\n".join(line for line in paragraph.splitlines()
                                  if not line.startswith(("#", "source:"))).strip()
            if not paragraph:
                continue
            for offset in range(0, len(paragraph), 1000):
                number += 1
                chunks.append({"doc_id": doc["doc_id"], "chunk_id": f"{doc['doc_id']}:{number}",
                               "title": doc["title"], "section": section, "page": None,
                               "source": doc["source"], "text": paragraph[offset:offset + 1000]})
    return chunks


class KnowledgeIndex:
    def __init__(self, snapshot: dict):
        self.snapshot = snapshot
        self.chunks = snapshot["chunks"]
        if not self.chunks:
            raise ValueError("知识资料没有可索引正文")
        self.vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4))
        self.matrix = self.vectorizer.fit_transform([
            f"{c['title']} {c['section']} {c['text']}" for c in self.chunks
        ])

    @classmethod
    def build(cls, directory: Path, index_dir: Path) -> "KnowledgeIndex":
        documents = read_documents(directory)
        snapshot = {"schema_version": 1, "corpus_sha256": corpus_hash(documents),
                    "retrieval": {"analyzer": "char", "ngram_range": [2, 4]},
                    "documents": documents, "chunks": split_documents(documents)}
        index = cls(snapshot)
        index_dir.mkdir(parents=True, exist_ok=True)
        target = index_dir / "index.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        return index

    @classmethod
    def load(cls, index_dir: Path, knowledge_dir: Path) -> "KnowledgeIndex":
        path = index_dir / "index.json"
        if not path.exists():
            raise ValueError("索引不存在，请先执行 python cli.py build-index")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if snapshot.get("schema_version") != 1:
            raise ValueError("索引版本不兼容，请重新建库")
        if snapshot["corpus_sha256"] != corpus_hash(read_documents(knowledge_dir)):
            raise ValueError("知识资料已修改，请重新 build-index")
        return cls(snapshot)

    def search(self, query: str, top_k: int = 4, min_score: float = 0.05) -> dict:
        if not query.strip() or not 1 <= top_k <= 20:
            raise ValueError("查询不能为空，top_k 必须为 1..20")
        scores = (self.matrix @ self.vectorizer.transform([query]).T).toarray().ravel()
        hits = [dict(self.chunks[int(i)], score=float(scores[i]))
                for i in scores.argsort()[::-1][:top_k] if scores[i] >= min_score]
        return {"query": query, "hits": hits, "evidence_status": "found" if hits else "insufficient"}
