"""Append-only events and final manifest for one run. Credentials are redacted."""
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4


def serializable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


class RunTrace:
    def __init__(self, runs_dir: Path, secrets: tuple[str, ...] = ()):
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        self.directory = runs_dir / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.secrets = tuple(s for s in secrets if s)

    def encode(self, value) -> str:
        content = json.dumps(value, ensure_ascii=False, default=serializable, allow_nan=False)
        for secret in self.secrets:
            content = content.replace(json.dumps(secret, ensure_ascii=False)[1:-1], "[REDACTED]")
        return content

    def event(self, event: str, **payload) -> None:
        row = {"run_id": self.run_id, "time": datetime.now(timezone.utc).isoformat(),
               "event": event, **payload}
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(self.encode(row) + "\n")

    def finish(self, **payload) -> None:
        (self.directory / "result.json").write_text(
            self.encode({"run_id": self.run_id, **payload}), encoding="utf-8")
