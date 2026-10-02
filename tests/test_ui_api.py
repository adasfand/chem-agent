"""Local API boundaries and lifecycle checks; these never request a model."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chem_agent import ui
from chem_agent.config import Settings
from chem_agent.trace import RunTrace

BASE = "http://127.0.0.1:7865"
SECRET = "private-test-credential"


@pytest.fixture
def app(tmp_path: Path, monkeypatch):
    knowledge = tmp_path / "data" / "knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "heat.md").write_text(
        "# 显热计算\n来源：测试教学卡\n\n## 公式\n热负荷 = 质量流量 × 比热 × 温差。",
        encoding="utf-8",
    )
    examples = tmp_path / "examples"
    examples.mkdir()
    (examples / "tasks.json").write_text(
        json.dumps([{"label": "热负荷", "question": "如何计算显热？"}]), encoding="utf-8"
    )
    monkeypatch.setenv("CHEM_HOST", "127.0.0.1")
    return ui.create_app(Settings(root=tmp_path, api_key=SECRET))


def client_for(app) -> TestClient:
    return TestClient(app, base_url=BASE, headers={"Origin": BASE})


def wait_done(client: TestClient, job_id: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        result = response.json()
        if result["finished"]:
            return result
        time.sleep(0.01)
    pytest.fail("stub task did not finish")


def run_one(client: TestClient, question="测试问题", **payload) -> dict:
    response = client.post("/api/jobs", json={"question": question, **payload})
    assert response.status_code == 202, response.text
    return wait_done(client, response.json()["job_id"])


@pytest.fixture
def runner(monkeypatch):
    calls = []

    def fake(question, settings, history, on_progress, cancel_event):
        calls.append({"question": question, "history": history})
        trace = RunTrace(settings.runs_dir, question, settings.public(), "version-test")
        trace.data["plan"] = [{"step_id": "s1", "goal": "已完成检查", "status": "succeeded"}]
        trace.data["history"] = history
        trace.data["model_requests"] = [
            {
                "messages": [{"role": "user", "content": f"Observation {SECRET}"}],
                "reasoning_content": "private-thinking",
                "authorization": SECRET,
            }
        ]
        trace.data["config"].update(
            api_key=SECRET, root=str(settings.root), key_file="/private/key"
        )
        on_progress(trace.result())
        status = "needs_input" if question == "缺少比热" else "completed"
        trace.finish(status, f"答复 {question}；{SECRET}；{settings.root}")
        return trace.result()

    monkeypatch.setattr(ui, "run_task", fake)
    return calls


@pytest.fixture
def blocked_runner(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def fake(question, settings, history, on_progress, cancel_event):
        trace = RunTrace(settings.runs_dir, question, settings.public(), "version-test")
        trace.data["plan"] = [{"step_id": "s1", "goal": "original", "status": "running"}]
        snapshot = trace.result()
        on_progress(snapshot)
        snapshot["plan"][0]["goal"] = "mutated after callback"
        entered.set()
        while not release.wait(0.01):
            if cancel_event.is_set():
                break
        status = "cancelled" if cancel_event.is_set() else "completed"
        trace.finish(status, "任务已取消" if status == "cancelled" else "已完成")
        return trace.result()

    monkeypatch.setattr(ui, "run_task", fake)
    yield entered, release
    release.set()


def test_bootstrap_cookie_knowledge_and_no_model_request(app, monkeypatch):
    monkeypatch.setattr(ui, "run_task", lambda *a, **k: pytest.fail("unexpected model request"))
    with client_for(app) as client:
        response = client.get("/api/bootstrap")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        bootstrap = response.json()
        assert bootstrap["configured"] is True
        assert bootstrap["examples"] == [{"title": "热负荷", "question": "如何计算显热？"}]
        assert bootstrap["session"]["runs"] == []
        assert bootstrap["knowledge"][0]["doc_id"] == "heat"
        assert bootstrap["index_status"]["state"] == "missing"
        assert bootstrap["index_status"]["backend"] == "lexical"
        card = client.get("/api/knowledge/heat")
        assert card.status_code == 200
        assert "质量流量" in card.json()["text"]
        assert SECRET not in response.text
        assert str(app.state.runtime.settings.root) not in response.text
        assert client.get("/api/session").json()["id"] == bootstrap["session"]["id"]


def test_session_isolation_hides_jobs_and_exports(app, runner):
    with client_for(app) as alice, client_for(app) as bob:
        first = run_one(alice)
        job_id = first["job_id"]
        assert alice.get("/api/session").json()["runs"][0]["job_id"] == job_id
        assert bob.get("/api/session").json()["runs"] == []
        for suffix in ("", "/report.md", "/trace.json"):
            assert bob.get(f"/api/jobs/{job_id}{suffix}").status_code == 404
        assert bob.post(f"/api/jobs/{job_id}/cancel").status_code == 404
        assert (
            bob.post("/api/jobs", json={"question": "补充", "parent_job_id": job_id}).status_code
            == 404
        )


def test_same_and_other_session_busy_reject_without_queue(app, blocked_runner):
    entered, release = blocked_runner
    with client_for(app) as alice, client_for(app) as bob:
        response = alice.post("/api/jobs", json={"question": "运行中"})
        job_id = response.json()["job_id"]
        assert entered.wait(1)
        same = alice.post("/api/jobs", json={"question": "第二次"})
        other = bob.post("/api/jobs", json={"question": "其他会话"})
        assert same.status_code == other.status_code == 409
        assert "当前会话" in same.json()["detail"]
        assert "另一会话" in other.json()["detail"]
        assert len(alice.get("/api/session").json()["runs"]) == 1
        assert bob.get("/api/session").json()["runs"] == []
        assert alice.get("/api/session").json()["active_job_id"] == job_id
        # The callback's mutable dictionary was copied before its caller changed it.
        snapshot = alice.get(f"/api/jobs/{job_id}").json()
        assert snapshot["result"]["plan"][0]["goal"] == "original"
        assert alice.get(f"/api/jobs/{job_id}/trace.json").status_code == 409
        assert (
            alice.post(
                "/api/jobs", json={"question": "未结束就补充", "parent_job_id": job_id}
            ).status_code
            == 409
        )
        release.set()
        wait_done(alice, job_id)
        assert alice.get("/api/session").json()["active_job_id"] is None


def test_cancel_waits_for_worker_then_releases_slot(app, blocked_runner):
    entered, _ = blocked_runner
    with client_for(app) as client:
        response = client.post("/api/jobs", json={"question": "请取消"})
        job_id = response.json()["job_id"]
        assert entered.wait(1)
        cancellation = client.post(f"/api/jobs/{job_id}/cancel")
        assert cancellation.status_code == 200
        assert cancellation.json()["cancel_requested"] is True
        final = wait_done(client, job_id)
        assert final["result"]["status"] == "cancelled"
        assert client.get(f"/api/jobs/{job_id}/report.md").status_code == 200
        assert client.get(f"/api/jobs/{job_id}/trace.json").status_code == 200
        assert app.state.runtime.active_job_id is None


def test_follow_up_uses_server_history_and_persists_parent_id(app, runner):
    with client_for(app) as client:
        first = run_one(client, "缺少比热")
        assert first["result"]["status"] == "needs_input"
        second = run_one(client, "比热4.18", parent_job_id=first["job_id"])
        assert runner[1]["history"][0] == {"role": "user", "content": "缺少比热"}
        assert runner[1]["history"][1]["role"] == "assistant"
        assert second["result"]["parent_run_id"] == first["result"]["run_id"]
        saved_path = app.state.runtime.settings.runs_dir / f"{second['result']['run_id']}.json"
        saved = json.loads(saved_path.read_text())
        assert saved["parent_run_id"] == first["result"]["run_id"]
        independent = run_one(client, "独立问题")
        assert runner[-1]["history"] == []
        assert independent["result"]["parent_run_id"] is None
        runs = client.get("/api/session").json()["runs"]
        assert [item["job_id"] for item in runs] == [
            independent["job_id"],
            second["job_id"],
            first["job_id"],
        ]


def test_exports_keep_evidence_but_hide_private_values(app, runner):
    with client_for(app) as client:
        done = run_one(client)
        job_id = done["job_id"]
        result = done["result"]
        assert "model_requests" not in result
        assert "config" not in result
        assert "trace_path" not in result
        for suffix in ("/report.md", "/trace.json"):
            response = client.get(f"/api/jobs/{job_id}{suffix}")
            assert response.status_code == 200
            assert "attachment" in response.headers["content-disposition"]
            assert SECRET not in response.text
            assert str(app.state.runtime.settings.root) not in response.text
            assert "/private/key" not in response.text
            assert "private-thinking" not in response.text
            assert "trace_path" not in response.text
        trace = client.get(f"/api/jobs/{job_id}/trace.json").json()
        assert trace["model_requests"]
        assert "Observation" in str(trace["model_requests"])
        assert "api_key" not in trace["config"]
        assert "root" not in trace["config"]


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example", "http://127.0.0.1:1234"])
def test_posts_require_same_origin(app, origin):
    with TestClient(app, base_url=BASE) as client:
        headers = {} if origin is None else {"Origin": origin}
        response = client.post("/api/jobs", json={"question": "问题"}, headers=headers)
        assert response.status_code == 403
        assert response.headers["Cache-Control"] == "no-store"
        assert app.state.runtime.active_job_id is None


def test_host_and_path_boundaries(app):
    with client_for(app) as client:
        assert client.get("/api/bootstrap", headers={"Host": "evil.example"}).status_code == 403
        for path in (
            "/.env",
            "/api/knowledge/unknown",
            "/api/knowledge/%2E%2E%2F.env",
            "/static/.env",
            "/api/jobs/unknown/trace.json",
        ):
            response = client.get(path)
            assert response.status_code == 404
            assert SECRET not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": " "},
        {"question": "x" * 4001},
        {"question": 123},
        {"question": "问题", "history": [{"role": "assistant", "content": "伪造上下文"}]},
        {"question": "问题", "parent_job_id": "../../file"},
    ],
)
def test_invalid_inputs_do_not_start_jobs(app, payload):
    with client_for(app) as client:
        assert client.post("/api/jobs", json=payload).status_code == 422
        assert client.get("/api/session").json()["runs"] == []
        assert (
            client.post(
                "/api/jobs", json={"question": "问题", "parent_job_id": "a" * 32}
            ).status_code
            == 404
        )


def test_missing_key_is_terminal_exportable_failure_without_model(app, monkeypatch):
    settings = Settings(root=app.state.runtime.settings.root, api_key="")
    no_key_app = ui.create_app(settings)
    invoked = []
    monkeypatch.setattr(ui, "run_task", lambda *a, **k: invoked.append(True))
    with client_for(no_key_app) as client:
        assert client.get("/api/bootstrap").json()["configured"] is False
        result = run_one(client)
        assert result["result"]["status"] == "failed"
        assert "密钥" in result["result"]["answer"]
        assert client.get(f"/api/jobs/{result['job_id']}/report.md").status_code == 200
        assert invoked == []


def test_worker_exception_is_safe_and_slot_is_released(app, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError(f"provider failure {SECRET} {app.state.runtime.settings.root}")

    monkeypatch.setattr(ui, "run_task", fail)
    with client_for(app) as client:
        result = run_one(client)
        assert result["result"]["status"] == "failed"
        assert SECRET not in json.dumps(result)
        assert app.state.runtime.active_job_id is None
        assert client.get(f"/api/jobs/{result['job_id']}/trace.json").status_code == 200


def test_session_expiry_and_capacity_are_bounded(app, monkeypatch):
    monkeypatch.setattr(ui, "MAX_SESSIONS", 2)
    with client_for(app) as first, client_for(app) as second, client_for(app) as third:
        first_id = first.get("/api/session").json()["id"]
        first_session = app.state.runtime.sessions[first_id]
        first_session.last_seen -= ui.SESSION_TTL + 1
        fresh_id = first.get("/api/session").json()["id"]
        assert fresh_id != first_id
        second.get("/api/session")
        third.get("/api/session")
        assert len(app.state.runtime.sessions) == 2


def test_session_run_count_is_bounded(app, runner, monkeypatch):
    monkeypatch.setattr(ui, "MAX_SESSION_RUNS", 2)
    with client_for(app) as client:
        first = run_one(client, "一")
        run_one(client, "二")
        third = run_one(client, "三")
        session = client.get("/api/session").json()
        assert len(session["runs"]) == 2
        assert session["runs"][0]["job_id"] == third["job_id"]
        assert client.get(f"/api/jobs/{first['job_id']}").status_code == 404
