"""Small, inspectable knowledge retrieval; indexes are rebuilt from text files."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer

_ALIASES = {
    "加热器功率": "热负荷",
    "加热功率": "热负荷",
    "加热负荷": "热负荷",
    "升温功率": "热负荷",
    "热功率": "热负荷",
    "heat duty": "热负荷",
    "specific heat capacity": "比热容",
    "specific heat": "比热容",
    "比热容量": "比热容",
    "比热容": "比热容",
    "比热": "比热容",
    "mass flow rate": "质量流量",
    "质量流率": "质量流量",
    "每小时": "/h",
    "每秒钟": "/s",
    "每秒": "/s",
    "千克": "kg",
    "公斤": "kg",
    "千焦耳": "kj",
    "千焦": "kj",
    "千瓦": "kw",
    "摄氏度": "°c",
    "开尔文": "k",
    "mass fraction": "质量分数",
    "质量百分比": "质量分数",
    "质量百分数": "质量分数",
    "质量占比": "质量分数",
    "含盐率": "盐质量分数",
    "含盐量": "盐质量分数",
    # Expand ambiguous colloquial concentration queries without deciding their basis.
    "盐浓度": "盐浓度 质量分数 摩尔分数 浓度口径",
    "mass balance": "物料衡算",
    "物料平衡": "物料衡算",
    "混合平衡": "混合衡算",
    "混配": "混合",
    "掺混": "混合",
    "温度差": "温差",
    "升高多少度": "温差",
}
_ALIAS_PATTERN = re.compile(
    "|".join(re.escape(key) for key in sorted(_ALIASES, key=len, reverse=True))
)
_SOURCE_PATTERN = re.compile(r"^来源\s*[:：]\s*(.+)$", re.MULTILINE)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _ALIAS_PATTERN.sub(lambda match: _ALIASES[match.group()], text)
    return re.sub(r"\s+", "", text)


@dataclass(frozen=True)
class _Chunk:
    doc_id: str
    chunk_id: str
    title: str
    text: str
    source: str


class KnowledgeBase:
    """Search local MD/TXT cards and return their original, attributable text.

    Construct a new instance after editing files. No serialized Python objects or
    model service are needed. Scores blend body/title cosine similarities; they
    are not probabilities or a guarantee that the excerpt answers the question.
    """

    min_score = 0.08

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._chunks: list[_Chunk] = []
        self._inventory: list[dict[str, Any]] = []
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        self._title_matrix = None
        digest = hashlib.sha256()
        root = self.directory.resolve()
        files = []
        for path in sorted(self.directory.rglob("*")):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("知识目录不支持符号链接文件。")
            if path.is_file():
                files.append(path)
        for path in files:
            relative = path.relative_to(self.directory).as_posix()
            raw = path.read_bytes()
            # Length-delimited inputs avoid ambiguous path/content concatenation.
            for part in (relative.encode("utf-8"), raw):
                digest.update(len(part).to_bytes(8, "big"))
                digest.update(part)
            text = raw.decode("utf-8-sig")
            if not text.strip():
                continue
            doc_id = path.relative_to(self.directory).with_suffix("").as_posix()
            title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else path.stem
            source_match = _SOURCE_PATTERN.search(text)
            source = source_match.group(1).strip() if source_match else "来源未注明"
            chunks = self._split_card(doc_id, title, source, text)
            self._chunks.extend(chunks)
            self._inventory.append(
                {
                    "doc_id": doc_id,
                    "title": title,
                    "source": source,
                    "chunk_count": len(chunks),
                }
            )
        self.version = digest.hexdigest()
        if self._chunks:
            self._vectorizer = TfidfVectorizer(
                analyzer="char", ngram_range=(2, 4), sublinear_tf=True, norm="l2"
            )
            corpus = [
                _normalize(f"{chunk.title}\n{chunk.title}\n{chunk.text}") for chunk in self._chunks
            ]
            # Cards containing no usable bigrams remain visible in the inventory.
            if any(len(document) >= 2 for document in corpus):
                self._matrix = self._vectorizer.fit_transform(corpus)
                self._title_matrix = self._vectorizer.transform(
                    [_normalize(chunk.title) for chunk in self._chunks]
                )

    @staticmethod
    def _split_card(doc_id: str, title: str, source: str, text: str) -> list[_Chunk]:
        body = re.sub(r"^#\s+.+\n?", "", text, count=1, flags=re.MULTILINE)
        body = _SOURCE_PATTERN.sub("", body).strip()
        sections = re.split(r"(?=^##\s+)", body, flags=re.MULTILINE)
        chunks: list[_Chunk] = []
        seen: dict[str, int] = {}
        for section in sections:
            section = section.strip()
            if not section:
                continue
            heading = re.match(r"^##\s+(.+)", section)
            identity = heading.group(1).strip() if heading else "body"
            ordinal = seen.get(identity, 0)
            seen[identity] = ordinal + 1
            section_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
            suffix = f"-{ordinal + 1}" if ordinal else ""
            chunks.append(
                _Chunk(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}:{section_hash}{suffix}",
                    title=title,
                    text=f"# {title}\n{section}",
                    source=source,
                )
            )
        return chunks

    def inventory(self) -> list[dict[str, Any]]:
        """Return document metadata without exposing internal mutable state."""
        return [dict(item) for item in self._inventory]

    def search(self, query: str, top_k: int = 3) -> dict[str, Any]:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 10:
            raise ValueError("top_k 必须是 1 至 10 的整数")
        if not isinstance(query, str):
            raise TypeError("query 必须是字符串")
        result: dict[str, Any] = {"query": query, "hits": [], "status": "no_evidence"}
        normalized = _normalize(query)
        if not normalized or self._vectorizer is None or self._matrix is None:
            return result
        vector = self._vectorizer.transform([normalized])
        body_scores = (self._matrix @ vector.T).toarray().ravel()
        title_scores = (self._title_matrix @ vector.T).toarray().ravel()
        # Short questions should not lose a direct title match in long formula text.
        scores = 0.75 * body_scores + 0.25 * title_scores
        ranked = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
        best = float(scores[ranked[0]]) if ranked else 0.0
        cutoff = max(self.min_score, best * 0.35)
        for index in ranked:
            score = float(scores[index])
            if score < cutoff or len(result["hits"]) >= top_k:
                break
            chunk = self._chunks[index]
            result["hits"].append(
                {
                    "doc_id": chunk.doc_id,
                    "chunk_id": chunk.chunk_id,
                    "title": chunk.title,
                    "text": chunk.text,
                    "source": chunk.source,
                    "score": round(score, 6),
                }
            )
        if result["hits"]:
            result["status"] = "ok"
        return result
