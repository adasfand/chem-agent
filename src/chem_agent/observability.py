"""Derive public context-injection evidence from actual recorded provider requests."""

import json


def context_evidence(result: dict) -> list[dict]:
    contexts = []
    for request in result.get("model_requests", []):
        if request.get("status") != "succeeded":
            contexts.append("")
            continue
        texts = []
        for message in request.get("messages", []):
            if message.get("role") != "user":
                continue
            content = message.get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                texts.extend(
                    block["text"]
                    for block in content
                    if isinstance(block, dict) and isinstance(block.get("text"), str)
                )
        contexts.append("\n".join(texts))
    evidence = []
    for hit in result.get("evidence", []):
        text, chunk_id = hit.get("text", ""), hit.get("chunk_id", "")
        if not text or not chunk_id:
            continue
        encodings = (text, repr(text), json.dumps(text, ensure_ascii=False))
        indices = [
            index + 1
            for index, context in enumerate(contexts)
            if chunk_id in context and any(encoded in context for encoded in encodings)
        ]
        if indices:
            evidence.append(
                {
                    "chunk_id": chunk_id,
                    "title": hit.get("title", "知识片段"),
                    "request_indices": indices,
                }
            )
    return evidence
