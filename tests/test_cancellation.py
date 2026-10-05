"""Cancellation prevents pending model actions without making network requests."""

import json
import threading

import pytest
from smolagents import Model, OpenAIModel
from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction

from chem_agent.agent import run_task
from chem_agent.config import Settings
from chem_agent.model import ModelUnavailable, RunCancelled, TracedModel
from chem_agent.tools import BusinessTool, FinalTool, PlanTool
from chem_agent.trace import RunTrace


@pytest.fixture
def settings(tmp_path):
    cards = tmp_path / "data" / "knowledge"
    cards.mkdir(parents=True)
    (cards / "units.md").write_text(
        "# 单位换算\n来源：离线测试\n\n压力单位 MPa 和 kPa 可相互换算。\n", encoding="utf-8"
    )
    return Settings(root=tmp_path, api_key="offline-dummy-key", max_steps=8)


def tool_response(name, arguments):
    return ChatMessage(
        role="assistant",
        content="",
        tool_calls=[
            ChatMessageToolCall(
                id="offline-call",
                type="function",
                function=ChatMessageToolCallFunction(name=name, arguments=arguments),
            )
        ],
    )


def test_pre_cancelled_task_never_initializes_model(settings):
    cancelled = threading.Event()
    cancelled.set()

    def factory(*_args):
        pytest.fail("A cancelled task must not initialize a model.")

    result = run_task("换算 1 MPa", settings, model_factory=factory, cancel_event=cancelled)
    assert result["status"] == "cancelled"
    assert result["calls"] == []
    assert result["model_requests"] == []
    saved = json.loads(
        settings.runs_dir.joinpath(f"{result['run_id']}.json").read_text(encoding="utf-8")
    )
    assert saved["status"] == "cancelled"


def test_provider_response_after_cancel_is_not_returned_to_agent(settings, monkeypatch):
    cancelled = threading.Event()
    trace = RunTrace(settings.runs_dir, "换算 1 MPa", {}, "offline-test")

    def provider_response(_model, *_args, **_kwargs):
        trace.data["model_requests"].append({"status": "pending"})
        cancelled.set()
        return tool_response("convert_units", {"value": 1})

    monkeypatch.setattr(OpenAIModel, "generate", provider_response)
    model = TracedModel(settings, trace)
    model.cancel_event = cancelled
    try:
        with pytest.raises(RunCancelled):
            model.generate([])
    finally:
        model.client.close()
    # The request itself succeeded; cancellation only prevents consuming its action.
    assert trace.data["model_requests"][-1]["status"] == "succeeded"
    assert trace.data["calls"] == []


def test_cancellation_keeps_completed_steps_and_blocks_late_tool(settings):
    cancelled = threading.Event()

    class LateResponseModel(Model):
        def __init__(self):
            super().__init__(model_id="offline-test")
            self.calls = 0

        def generate(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return tool_response(
                    "set_plan",
                    {
                        "steps": [
                            {
                                "step_id": step,
                                "goal": "换算压力",
                                "tool_name": "convert_units",
                                "depends_on": [],
                            }
                            for step in ("s1", "s2")
                        ]
                    },
                )
            if self.calls == 3:
                cancelled.set()
            return tool_response(
                "convert_units",
                {
                    "step_id": f"s{self.calls - 1}",
                    "arguments": {"value": 1, "from_unit": "MPa", "to_unit": "kPa"},
                },
            )

    model = LateResponseModel()
    result = run_task(
        "分别换算两股压力 1 MPa",
        settings,
        model_factory=lambda *_args: model,
        cancel_event=cancelled,
    )
    assert result["status"] == "cancelled"
    assert model.calls == 3
    assert len(result["calls"]) == 1
    assert result["calls"][0]["output"]["value"] == 1000
    assert [step["status"] for step in result["plan"]] == ["succeeded", "pending"]


@pytest.mark.parametrize("kind", ["plan", "business", "final"])
def test_all_tool_entry_points_check_cancellation(kind):
    cancelled = threading.Event()
    cancelled.set()
    # A sentinel proves the execution layer is never reached after cancellation.
    execution = object()
    tools = {
        "plan": (PlanTool(execution, cancelled), {"steps": []}),
        "business": (
            BusinessTool("convert_units", execution, cancelled),
            {"step_id": "s1", "arguments": {}},
        ),
        "final": (
            FinalTool(execution, cancelled),
            {"answer": "完成", "status": "completed", "citations": []},
        ),
    }
    tool, arguments = tools[kind]
    with pytest.raises(RunCancelled):
        tool.forward(**arguments)


def test_cancelled_inflight_request_failure_remains_cancelled(settings):
    cancelled = threading.Event()

    class FailingModel(Model):
        def generate(self, *_args, **_kwargs):
            cancelled.set()
            raise ModelUnavailable("模型请求失败或超时。")

    result = run_task(
        "换算 1 MPa",
        settings,
        model_factory=lambda *_args: FailingModel(model_id="offline-test"),
        cancel_event=cancelled,
    )
    assert result["status"] == "cancelled"
    assert result["calls"] == []
