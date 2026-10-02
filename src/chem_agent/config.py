"""Local configuration; never serialize credentials into run records."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    root: Path
    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    request_timeout: float = 60
    max_steps: int = 12

    @property
    def knowledge_dir(self) -> Path:
        return self.root / "data" / "knowledge"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    def public(self) -> dict:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "request_timeout": self.request_timeout,
            "max_steps": self.max_steps,
        }

    @classmethod
    def load(cls, root: Path | None = None) -> Settings:
        root = (root or Path(os.environ.get("CHEM_PROJECT_ROOT", Path.cwd()))).resolve()
        config = {**dotenv_values(root / ".env"), **os.environ}
        key = config.get("DEEPSEEK_API_KEY", "") or ""
        key_file = config.get("DEEPSEEK_API_KEY_FILE", "")
        if not key and key_file:
            path = Path(key_file).expanduser()
            if not path.is_absolute():
                path = root / path
            try:
                key = path.read_text(encoding="utf-8").strip()
            except OSError:
                raise ValueError(
                    "无法读取 DEEPSEEK_API_KEY_FILE，请检查本机配置和文件权限。"
                ) from None
        base_url = config.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        parsed = urlparse(base_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("模型地址不能包含凭据、查询参数或片段。")
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("模型地址需要使用 HTTPS；本地服务可使用 HTTP。")
        timeout = float(config.get("CHEM_REQUEST_TIMEOUT") or 60)
        steps = int(config.get("CHEM_MAX_STEPS") or 12)
        if not 1 <= timeout <= 180 or not 2 <= steps <= 20:
            raise ValueError("请求超时应为 1–180 秒，最大执行步数应为 2–20。")
        return cls(
            root=root,
            api_key=key,
            base_url=base_url,
            model=config.get("DEEPSEEK_MODEL") or "deepseek-v4-pro",
            request_timeout=timeout,
            max_steps=steps,
        )
