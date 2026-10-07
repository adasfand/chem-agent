"""Local FastAPI workbench with isolated sessions and one visible model slot."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from chem_agent import __version__
from chem_agent.agent import run_task
from chem_agent.config import Settings
from chem_agent.retrieval import HybridRetriever
from chem_agent.trace import RunTrace, redact, utc_now

COOKIE_NAME = "chem_session"
SESSION_TTL = 24 * 60 * 60
MAX_SESSIONS = 128
MAX_SESSION_RUNS = 40
WEB_DIR = Path(__file__).parent / "web"
TERMINAL_STATUSES = {
    "completed",
    "needs_input",
    "no_evidence",
    "failed",
    "out_of_scope",
    "cancelled",
}
_RUN_ID = re.compile(r"\d{8}T\d{6}-[a-f0-9]{10}")
_REQUEST_ID = re.compile(
    r"(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12})"
)
_JOB_ID = re.compile(r"[a-f0-9]{32}")
logger = logging.getLogger(__name__)


class JobInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question: str = Field(min_length=1, max_length=4000)
    parent_job_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    client_request_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("问题不能为空")
        return value


@dataclass
class _Job:
    id: str
    question: str
    created_at: str
    result: dict[str, Any]
    history: list[dict[str, str]] = field(default_factory=list)
    parent_run_id: str | None = None
    parent_job_id: str | None = None
    client_request_id: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    finished: bool = False


@dataclass
class _Session:
    id: str
    last_seen: float
    jobs: dict[str, _Job] = field(default_factory=dict)
    active_job_id: str | None = None


class _Runtime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.knowledge = HybridRetriever(settings)
        self.lock = threading.RLock()
        self.sessions: dict[str, _Session] = {}
        self.active_job_id: str | None = None
        self.secrets = (settings.api_key, str(settings.root.resolve()))

    def session(self, session_id: str | None) -> tuple[_Session, bool]:
        now = time.monotonic()
        with self.lock:
            expired = [
                key
                for key, value in self.sessions.items()
                if not value.active_job_id and now - value.last_seen > SESSION_TTL
            ]
            for key in expired:
                del self.sessions[key]
            if session_id in self.sessions:
                current = self.sessions[session_id]
                current.last_seen = now
                return current, False
            if len(self.sessions) >= MAX_SESSIONS:
                removable = [s for s in self.sessions.values() if not s.active_job_id]
                if not removable:
                    raise HTTPException(503, "会话已满，请稍后重试。")
                del self.sessions[min(removable, key=lambda s: s.last_seen).id]
            current = _Session(secrets.token_urlsafe(32), now)
            self.sessions[current.id] = current
            return current, True

    def clean_result(self, result: dict, *, include_requests: bool = False) -> dict:
        cleaned = redact(deepcopy(result), self.secrets)

        def remove_private(value):
            if isinstance(value, dict):
                return {
                    key: remove_private(item)
                    for key, item in value.items()
                    if key not in {"trace_path", "root", "reasoning_content"}
                    and not any(
                        part in key.lower() for part in ("api_key", "authorization", "password")
                    )
                }
            if isinstance(value, list):
                return [remove_private(item) for item in value]
            return value

        cleaned = remove_private(cleaned)
        if include_requests:
            allowed = {"model", "base_url", "request_timeout", "max_steps"}
            cleaned["config"] = {
                key: value for key, value in cleaned.get("config", {}).items() if key in allowed
            }
        else:
            cleaned.pop("model_requests", None)
            cleaned.pop("config", None)
        return cleaned

    def session_view(self, session: _Session) -> dict:
        with self.lock:
            return {
                "id": session.id,
                "active_job_id": session.active_job_id,
                "runs": [
                    {
                        "job_id": job.id,
                        "question": redact(job.question, self.secrets),
                        "status": job.result.get("status", "running"),
                        "created_at": job.created_at,
                        "run_id": job.result.get("run_id"),
                        "client_request_id": job.client_request_id,
                    }
                    for job in reversed(list(session.jobs.values()))
                ],
            }

    def job_view(self, job: _Job) -> dict:
        with self.lock:
            return {
                "job_id": job.id,
                "finished": job.finished,
                "cancel_requested": job.cancel.is_set(),
                "client_request_id": job.client_request_id,
                "result": self.clean_result(job.result),
            }

    def find_job(self, session: _Session, job_id: str) -> _Job:
        with self.lock:
            job = session.jobs.get(job_id)
            if job is None:
                raise HTTPException(404, "任务不存在或已过期。")
            return job

    def start(self, session: _Session, payload: JobInput) -> _Job:
        with self.lock:
            if payload.client_request_id:
                existing = next(
                    (
                        job
                        for job in session.jobs.values()
                        if job.client_request_id == payload.client_request_id
                    ),
                    None,
                )
                if existing is not None:
                    if (
                        existing.question != payload.question
                        or existing.parent_job_id != payload.parent_job_id
                    ):
                        raise HTTPException(409, "请求编号已用于其他输入，请新建任务后重试。")
                    return existing
            history: list[dict[str, str]] = []
            parent_run_id = None
            if payload.parent_job_id:
                parent = self.find_job(session, payload.parent_job_id)
                if not parent.finished:
                    raise HTTPException(409, "原任务尚未结束，请等待完成或取消后再补充。")
                parent_run_id = parent.result.get("run_id")
                history = (
                    deepcopy(parent.history)
                    + [
                        {"role": "user", "content": parent.question},
                        {"role": "assistant", "content": parent.result.get("answer", "")},
                    ]
                )[-8:]
            if session.active_job_id:
                raise HTTPException(409, "当前会话已有任务正在执行，请等待或取消后重试。")
            if self.active_job_id:
                raise HTTPException(409, "模型正在处理另一会话的任务，请稍后重试。")
            created_at = utc_now()
            job = _Job(
                id=secrets.token_hex(16),
                question=payload.question,
                created_at=created_at,
                history=history,
                parent_run_id=parent_run_id,
                parent_job_id=payload.parent_job_id,
                client_request_id=payload.client_request_id,
                result={
                    "status": "running",
                    "question": payload.question,
                    "started_at": created_at,
                    "parent_run_id": parent_run_id,
                    "plan": [],
                    "calls": [],
                    "evidence": [],
                    "citations": [],
                    "answer": "",
                },
            )
            if len(session.jobs) >= MAX_SESSION_RUNS:
                oldest = next(key for key in session.jobs if key != payload.parent_job_id)
                del session.jobs[oldest]
            session.jobs[job.id] = job
            session.active_job_id = self.active_job_id = job.id
            try:
                threading.Thread(
                    target=self.worker,
                    args=(session, job),
                    name=f"chem-agent-{job.id[:8]}",
                    daemon=True,
                ).start()
            except Exception:
                session.jobs.pop(job.id, None)
                session.active_job_id = self.active_job_id = None
                raise HTTPException(503, "任务无法启动，请稍后重试。") from None
            return job

    def persist_final(self, result: dict) -> None:
        """Called only after run_task returns, when its trace writer has stopped."""
        run_id = result.get("run_id", "")
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            return
        directory = self.settings.runs_dir
        directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
                json.dump(
                    self.clean_result(result, include_requests=True),
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
            temporary.replace(directory / f"{run_id}.json")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def fallback(self, job: _Job, status: str, answer: str) -> dict:
        # A startup/configuration failure should also be exportable without an API request.
        with self.lock:
            result = deepcopy(job.result)
        if not result.get("run_id"):
            try:
                trace = RunTrace(
                    self.settings.runs_dir,
                    job.question,
                    self.settings.public(),
                    self.knowledge.version,
                    self.secrets,
                    mode="not_started",
                )
                result = trace.result()
            except OSError:
                pass
        result.update(status=status, answer=answer, finished_at=utc_now(), history=job.history)
        return result

    def worker(self, session: _Session, job: _Job) -> None:
        started = time.perf_counter()
        error_type = "-"

        def progress(result: dict) -> None:
            snapshot = deepcopy(result)
            snapshot["parent_run_id"] = job.parent_run_id
            with self.lock:
                job.result = snapshot

        try:
            if job.cancel.is_set():
                result = self.fallback(job, "cancelled", "任务已取消。")
            elif not self.settings.api_key:
                result = self.fallback(job, "failed", "尚未配置模型密钥，请填写本机配置后重试。")
            else:
                result = run_task(
                    job.question,
                    self.settings,
                    history=deepcopy(job.history),
                    on_progress=progress,
                    cancel_event=job.cancel,
                )
            if result.get("status") not in TERMINAL_STATUSES:
                result = self.fallback(job, "failed", "本次任务未正常结束，请重试。")
        except Exception as exc:
            error_type = type(exc).__name__
            status = "cancelled" if job.cancel.is_set() else "failed"
            answer = (
                "任务已取消。" if status == "cancelled" else "任务执行失败，请检查本机配置后重试。"
            )
            result = self.fallback(job, status, answer)
        result = deepcopy(result)
        result["parent_run_id"] = job.parent_run_id
        try:
            self.persist_final(result)
        except (OSError, ValueError, TypeError) as exc:
            error_type = type(exc).__name__
            result["record_warning"] = "本地运行记录保存失败；可从当前页面导出。"
        finally:
            with self.lock:
                job.result = result
                job.finished = True
                session.active_job_id = None
                self.active_job_id = None
        run_id = result.get("run_id", "")
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            run_id = "-"
        logger.info(
            "task_finished job_id=%s run_id=%s status=%s latency_ms=%.3f error_type=%s",
            job.id,
            run_id,
            result["status"],
            (time.perf_counter() - started) * 1000,
            error_type,
        )


def _server_config(settings: Settings) -> dict:
    return {**dotenv_values(settings.root / ".env"), **os.environ}


def _origin_parts(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            return None
        return (
            parsed.scheme,
            parsed.hostname.lower(),
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


def create_app(settings: Settings) -> FastAPI:
    runtime = _Runtime(settings)
    config = _server_config(settings)
    allowed_hosts = {"localhost", "127.0.0.1", "::1"}
    configured_host = str(config.get("CHEM_HOST") or "127.0.0.1").lower()
    allowed_hosts.add(configured_host)
    app = FastAPI(title="化工知识与计算助手", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = runtime
    examples = json.loads((settings.root / "examples" / "tasks.json").read_text(encoding="utf-8"))
    inventory = runtime.knowledge.inventory()
    by_id = {item["doc_id"]: item for item in inventory}
    cards = {}
    knowledge_root = settings.knowledge_dir.resolve()
    for path in sorted(settings.knowledge_dir.rglob("*")):
        if (
            path.is_file()
            and path.suffix.lower() in {".md", ".txt"}
            and path.resolve().is_relative_to(knowledge_root)
        ):
            doc_id = path.relative_to(settings.knowledge_dir).with_suffix("").as_posix()
            if doc_id in by_id:
                cards[doc_id] = {
                    **by_id[doc_id],
                    "text": path.read_text(encoding="utf-8-sig"),
                }

    @app.middleware("http")
    async def local_session(request: Request, call_next):
        started = time.perf_counter()
        supplied_id = request.headers.get("x-request-id", "")
        request_id = (
            supplied_id.lower() if _REQUEST_ID.fullmatch(supplied_id) else secrets.token_hex(16)
        )
        request.state.request_id = request_id
        origin = _origin_parts(f"{request.url.scheme}://{request.headers.get('host', '')}")
        new_session = False
        current = None
        error_type = "-"
        try:
            if not origin or origin[1] not in allowed_hosts:
                raise HTTPException(403, "不允许此访问地址。")
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                if _origin_parts(request.headers.get("origin", "")) != origin:
                    raise HTTPException(403, "仅允许从当前页面提交请求。")
            # Health probes must not allocate or evict browser sessions.
            if request.url.path != "/health":
                current, new_session = runtime.session(request.cookies.get(COOKIE_NAME))
                request.state.chem_session = current
            response = await call_next(request)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        except Exception as exc:
            error_type = type(exc).__name__
            response = JSONResponse(
                {"detail": "服务暂时无法处理请求，请稍后重试。"}, status_code=500
            )
        if new_session and current is not None:
            response.set_cookie(
                COOKIE_NAME,
                current.id,
                max_age=SESSION_TTL,
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Request-ID"] = request_id
        route = getattr(request.scope.get("route"), "path", "unmatched")
        job_id = getattr(request.state, "job_id", request.path_params.get("job_id", ""))
        if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
            job_id = "-"
        method = (
            request.method
            if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            else "OTHER"
        )
        logger.info(
            "http_request request_id=%s method=%s route=%s status=%d "
            "latency_ms=%.3f job_id=%s error_type=%s",
            request_id,
            method,
            route,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            job_id,
            error_type,
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request, _exception):
        return JSONResponse(
            {"detail": "输入格式无效：请输入 1–4000 字的问题和有效的任务、请求编号。"},
            status_code=422,
        )

    @app.get("/")
    def index():
        path = WEB_DIR / "index.html"
        if not path.is_file():
            raise HTTPException(503, "页面资源尚未就绪。")
        return FileResponse(path, media_type="text/html")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "version": __version__,
            "model_configured": bool(settings.api_key),
            "retrieval": {
                "state": runtime.knowledge.index_status.get("state"),
                "backend": runtime.knowledge.index_status.get("backend"),
            },
        }

    @app.get("/static/{name}")
    def static_file(name: str):
        types = {"style.css": "text/css", "app.js": "application/javascript"}
        if name not in types or not (WEB_DIR / name).is_file():
            raise HTTPException(404, "资源不存在。")
        return FileResponse(WEB_DIR / name, media_type=types[name])

    @app.get("/api/bootstrap")
    def bootstrap(request: Request):
        return {
            "version": __version__,
            "model": settings.model,
            "configured": bool(settings.api_key),
            "examples": [
                {"title": e.get("title") or e.get("label") or "示例", "question": e["question"]}
                for e in examples
            ],
            "knowledge": inventory,
            "index_status": runtime.knowledge.index_status,
            "session": runtime.session_view(request.state.chem_session),
        }

    @app.get("/api/session")
    def session_info(request: Request):
        return runtime.session_view(request.state.chem_session)

    @app.post("/api/jobs", status_code=202)
    def new_job(payload: JobInput, request: Request):
        job = runtime.start(request.state.chem_session, payload)
        request.state.job_id = job.id
        return runtime.job_view(job)

    @app.get("/api/jobs/{job_id}")
    def job_info(job_id: str, request: Request):
        return runtime.job_view(runtime.find_job(request.state.chem_session, job_id))

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, request: Request):
        job = runtime.find_job(request.state.chem_session, job_id)
        with runtime.lock:
            if not job.finished:
                job.cancel.set()
            return runtime.job_view(job)

    def final_snapshot(job_id: str, request: Request) -> dict:
        job = runtime.find_job(request.state.chem_session, job_id)
        with runtime.lock:
            if not job.finished:
                raise HTTPException(409, "任务尚未结束，请稍后导出。")
            return runtime.clean_result(job.result, include_requests=True)

    @app.get("/api/jobs/{job_id}/report.md")
    def report(job_id: str, request: Request):
        from chem_agent.report import render_report

        result = final_snapshot(job_id, request)
        # Reports receive only observable results; model requests belong in trace export.
        result.pop("model_requests", None)
        result.pop("config", None)
        return Response(
            render_report(result),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="report-{job_id}.md"'},
        )

    @app.get("/api/jobs/{job_id}/trace.json")
    def trace_download(job_id: str, request: Request):
        result = final_snapshot(job_id, request)
        return Response(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="trace-{job_id}.json"'},
        )

    @app.get("/api/knowledge/{doc_id:path}")
    def knowledge_card(doc_id: str):
        if doc_id not in cards:
            raise HTTPException(404, "知识卡不存在。")
        return cards[doc_id]

    return app


def launch(settings: Settings) -> None:
    import uvicorn
    from uvicorn.config import LOGGING_CONFIG

    config = _server_config(settings)
    log_config = deepcopy(LOGGING_CONFIG)
    log_config["loggers"]["chem_agent.ui"] = {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    uvicorn.run(
        create_app(settings),
        host=config.get("CHEM_HOST") or "127.0.0.1",
        port=int(config.get("CHEM_PORT") or 7860),
        access_log=False,
        log_config=log_config,
    )
