"""Configuration relative to an explicitly selected project root."""
from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    root: Path
    knowledge_dir: Path
    index_dir: Path
    runs_dir: Path
    model_id: str
    api_base: str
    api_key: str
    timeout: float
    max_steps: int
    planning_interval: int
    top_k: int
    min_score: float

    @classmethod
    def load(cls, root: Path) -> "Settings":
        root = root.resolve()
        load_dotenv(root / ".env", override=False)
        def path(key: str, default: str) -> Path:
            return (root / os.getenv(key, default)).resolve()
        result = cls(
            root, path("CHEM_KNOWLEDGE_DIR", "data/knowledge-example"),
            path("CHEM_INDEX_DIR", "data/index"), path("CHEM_RUNS_DIR", "runs"),
            os.getenv("CHEM_MODEL_ID", ""), os.getenv("CHEM_API_BASE", ""),
            os.getenv("CHEM_API_KEY", ""), float(os.getenv("CHEM_TIMEOUT", "60")),
            int(os.getenv("CHEM_MAX_STEPS", "12")),
            int(os.getenv("CHEM_PLANNING_INTERVAL", "3")),
            int(os.getenv("CHEM_TOP_K", "4")), float(os.getenv("CHEM_MIN_SCORE", "0.05")),
        )
        if not (0 < result.timeout < 3600 and 1 <= result.max_steps <= 30
                and 1 <= result.planning_interval <= 30 and 1 <= result.top_k <= 20
                and 0 < result.min_score <= 1):
            raise ValueError("配置范围错误：timeout/steps/planning_interval/top_k/min_score")
        return result

    def require_model(self) -> None:
        if not all((self.model_id, self.api_base, self.api_key)):
            raise ValueError("请在 .env 配置 CHEM_MODEL_ID、CHEM_API_BASE、CHEM_API_KEY")

    def public_summary(self) -> dict:
        return {"model_id": self.model_id, "max_steps": self.max_steps,
                "planning_interval": self.planning_interval, "top_k": self.top_k,
                "min_score": self.min_score, "timeout": self.timeout}
