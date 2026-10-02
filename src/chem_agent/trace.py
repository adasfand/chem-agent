"""Persist observable plans and executions, excluding private model reasoning."""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return f"[invalid non-finite number: {value}]"
    if isinstance(value, dict):
        return {
            str(k): "[redacted]"
            if any(word in str(k).lower() for word in ("api_key", "authorization", "password"))
            else redact(v, secrets)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        return re.sub(r"\bsk-[A-Za-z0-9_-]{10,}", "[redacted]", value)
    return value


class RunTrace:
    def __init__(self, directory: Path, question: str, config: dict, version: str, secrets=()):
        self.directory = directory
        self.secrets = tuple(secrets)
        self.run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:10]
        )
        self.path = directory / f"{self.run_id}.json"
        self.data = {
            "schema_version": 1,
            "run_id": self.run_id,
            "mode": "live",
            "started_at": utc_now(),
            "question": question,
            "config": config,
            "knowledge_version": version,
            "status": "running",
            "plan": [],
            "calls": [],
            "evidence": [],
            "model_requests": [],
            "answer": "",
            "citations": [],
        }
        self.save()

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        cleaned = redact(self.data, self.secrets)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def finish(self, status: str, answer: str, citations: list[str] | None = None) -> None:
        self.data.update(
            status=status, answer=answer, citations=citations or [], finished_at=utc_now()
        )
        self.save()

    def result(self) -> dict:
        return {**redact(self.data, self.secrets), "trace_path": str(self.path)}
