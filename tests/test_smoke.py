"""API -> real Agent -> retrieval/tools -> exports, with only the model scripted."""

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_agent import ScriptedModel

from chem_agent import ui
from chem_agent.agent import run_task
from chem_agent.config import Settings

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:7860"


def test_api_agent_tool_retrieval_and_export_smoke(tmp_path, monkeypatch):
    for directory in ("data", "examples"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    settings = Settings(root=tmp_path, api_key="offline-dummy-key", max_steps=8)

    def model_factory(_settings, trace):
        trace.data["mode"] = "offline_smoke"
        script = [
            (
                "set_plan",
                {
                    "steps": [
                        {"step_id": "s1", "goal": "检索显热", "tool_name": "search_knowledge"},
                        {"step_id": "s2", "goal": "换算流量", "tool_name": "convert_units"},
                        {
                            "step_id": "s3",
                            "goal": "计算显热",
                            "tool_name": "calc_heat_duty",
                            "depends_on": ["s1", "s2"],
                        },
                    ]
                },
            ),
            ("search_knowledge", {"step_id": "s1", "arguments": {"query": "显热热负荷公式"}}),
            (
                "convert_units",
                {
                    "step_id": "s2",
                    "arguments": {"value": 1000, "from_unit": "kg/h", "to_unit": "kg/s"},
                },
            ),
            (
                "calc_heat_duty",
                {
                    "step_id": "s3",
                    "arguments": {
                        "mass_flow_kg_s": {"$ref": "s2.value"},
                        "specific_heat_kj_kg_k": 4.18,
                        "delta_t_k": 40,
                    },
                },
            ),
        ]

        def action(index):
            if index < len(script):
                return script[index]
            return "final_answer", {
                "answer": "热负荷约46.44 kW，稳态恒比热，无相变和热损失。",
                "status": "completed",
                "citations": [trace.data["evidence"][0]["chunk_id"]],
            }

        return ScriptedModel(action)

    def runner(question, settings, **kwargs):
        result = run_task(question, settings, model_factory=model_factory, **kwargs)
        result["mode"] = "offline_smoke"
        return result

    monkeypatch.setattr(ui, "run_task", runner)
    with TestClient(ui.create_app(settings), base_url=BASE, headers={"Origin": BASE}) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        response = client.post(
            "/api/jobs",
            json={
                "question": "1000 kg/h液体升温40 K，比热4.18 kJ/(kg·K)，求热负荷。",
                "client_request_id": "a" * 32,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["finished"]:
                break
            time.sleep(0.01)
        else:
            pytest.fail("Offline Agent/API chain did not complete")
        result = job["result"]
        assert result["status"] == "completed"
        assert result["calls"][-1]["output"]["heat_duty_kw"] == pytest.approx(46.44444444444444)
        assert result["calls"][-1]["input_refs"][0]["ref"] == "s2.value"
        assert result["evidence"] and result["citations"]
        assert result["latency_ms"] >= 0
        report = client.get(f"/api/jobs/{job_id}/report.md")
        assert report.status_code == 200 and "46.4444444444" in report.text
        trace = client.get(f"/api/jobs/{job_id}/trace.json").json()
        assert trace["mode"] == "offline_smoke"
        assert trace["citations"] == result["citations"]
        assert (
            json.loads((tmp_path / "runs" / f"{trace['run_id']}.json").read_text())["status"]
            == "completed"
        )
