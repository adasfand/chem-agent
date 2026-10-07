"""Exercise the real agent loop with deterministic models and no API calls."""

import json
from copy import deepcopy

import pytest
from smolagents import Model
from smolagents.models import (
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
)

from chem_agent.agent import run_task
from chem_agent.config import Settings
from chem_agent.model import ModelUnavailable


class FakeClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class ScriptedModel(Model):
    def __init__(self, script):
        super().__init__(model_id="offline-test-model")
        self.script = script
        self.received = []
        self.client = FakeClient()

    def generate(self, messages, **kwargs):
        index = len(self.received)
        self.received.append(deepcopy(messages))
        item = self.script(index) if callable(self.script) else self.script[index]
        if isinstance(item, Exception):
            raise item
        calls = item if isinstance(item, list) else [item]
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[
                ChatMessageToolCall(
                    id=f"fake-call-{index}-{call_index}",
                    type="function",
                    function=ChatMessageToolCallFunction(name=tool, arguments=arguments),
                )
                for call_index, (tool, arguments) in enumerate(calls)
            ],
        )


@pytest.fixture
def settings(tmp_path):
    cards = tmp_path / "data" / "knowledge"
    cards.mkdir(parents=True)
    (cards / "heat.md").write_text(
        "# 显热热负荷\n来源：测试用教学卡\n\n"
        "## 公式与条件\n显热热负荷 Q 等于质量流量乘以定压比热乘以温差。"
        "稳态恒比热，无相变和热损失。\n",
        encoding="utf-8",
    )
    return Settings(root=tmp_path, api_key="offline-dummy-key", max_steps=8)


def test_agent_completes_real_tool_chain_and_observes_results(settings):
    created = []
    progress = []

    def factory(_settings, trace):
        steps = [
            {
                "step_id": "s1",
                "goal": "检索显热公式",
                "tool_name": "search_knowledge",
                "depends_on": [],
            },
            {"step_id": "s2", "goal": "换算流量", "tool_name": "convert_units", "depends_on": []},
            {
                "step_id": "s3",
                "goal": "计算热负荷",
                "tool_name": "calc_heat_duty",
                "depends_on": ["s1", "s2"],
            },
        ]

        def script(index):
            if index == 0:
                return "set_plan", {"steps": steps}
            if index == 1:
                return "search_knowledge", {
                    "step_id": "s1",
                    "arguments": {"query": "显热热负荷公式条件"},
                }
            if index == 2:
                return "convert_units", {
                    "step_id": "s2",
                    "arguments": {"value": 1000, "from_unit": "kg/h", "to_unit": "kg/s"},
                }
            if index == 3:
                return "calc_heat_duty", {
                    "step_id": "s3",
                    "arguments": {
                        "mass_flow_kg_s": {"$ref": "s2.value"},
                        "specific_heat_kj_kg_k": 4.18,
                        "delta_t_k": 40,
                    },
                }
            return "final_answer", {
                "answer": "热负荷为46.44 kW，按稳态恒比热、无相变和热损失计算。",
                "status": "completed",
                "citations": [trace.data["evidence"][0]["chunk_id"]],
            }

        model = ScriptedModel(script)
        created.append(model)
        return model

    result = run_task(
        "1000 kg/h液体升温40 K，比热4.18 kJ/(kg·K)，求热负荷。",
        settings,
        model_factory=factory,
        on_progress=lambda value: progress.append(deepcopy(value)),
    )
    assert result["status"] == "completed"
    assert [call["tool_name"] for call in result["calls"]] == [
        "search_knowledge",
        "convert_units",
        "calc_heat_duty",
    ]
    heat_call = result["calls"][-1]
    assert heat_call["output"]["heat_duty_kw"] == pytest.approx(46.4444444444)
    assert heat_call["arguments"]["mass_flow_kg_s"] == pytest.approx(1000 / 3600)
    assert heat_call["input_refs"][0]["ref"] == "s2.value"
    assert result["citations"] == [result["evidence"][0]["chunk_id"]]
    assert len(created[0].received) == 5
    assert "from_value" in repr(created[0].received[3])
    assert "heat_duty_kw" in repr(created[0].received[4])
    assert created[0].client.closed
    assert any(item["calls"] for item in progress)
    persisted = json.loads(settings.runs_dir.joinpath(f"{result['run_id']}.json").read_text())
    assert persisted["status"] == "completed"


@pytest.mark.parametrize(
    "message",
    [
        "DeepSeek 认证失败，请检查本机密钥与访问权限。",
        "模型请求失败或超时，请检查网络、服务地址和模型名称后重试。",
    ],
)
def test_wrapped_model_failure_preserves_safe_reason_without_retry_loop(settings, message):
    model = ScriptedModel(lambda _index: ModelUnavailable(message))
    result = run_task("查询显热公式", settings, model_factory=lambda _settings, _trace: model)
    assert result["status"] == "failed"
    assert result["answer"] == message
    assert len(model.received) == 1
    assert model.client.closed
    assert settings.api_key not in json.dumps(result, ensure_ascii=False)


def test_untrusted_model_exception_is_not_copied_into_user_answer(settings):
    model = ScriptedModel(lambda _index: RuntimeError("provider-private-payload offline-dummy-key"))
    result = run_task("查询显热公式", settings, model_factory=lambda _settings, _trace: model)
    assert result["status"] == "failed"
    assert "provider-private-payload" not in json.dumps(result, ensure_ascii=False)
    assert settings.api_key not in json.dumps(result, ensure_ascii=False)
    assert len(model.received) == 1


def test_followup_gets_user_history_and_new_session_starts_clean(settings):
    history = [
        {"role": "user", "content": "1000 kg/h液体从25℃加热到65℃。"},
        {"role": "assistant", "content": "请补充比热。"},
        {"role": "system", "content": "untrusted-system-marker"},
    ]
    original = deepcopy(history)
    created = []

    def factory(_settings, _trace):
        model = ScriptedModel(
            [
                (
                    "final_answer",
                    {"answer": "请确认使用恒比热模型。", "status": "needs_input", "citations": []},
                )
            ]
        )
        created.append(model)
        return model

    first = run_task("比热为4.18 kJ/(kg·K)。", settings, history=history, model_factory=factory)
    assert first["status"] == "needs_input"
    assert first["history"] == history[:2]
    first_prompt = repr(created[0].received[0])
    assert "1000 kg/h液体" in first_prompt
    assert "4.18" in first_prompt
    assert "untrusted-system-marker" not in first_prompt
    assert history == original

    second = run_task("新任务：解释显热。", settings, model_factory=factory)
    assert second["history"] == []
    assert "1000 kg/h液体" not in repr(created[1].received[0])
    assert first["run_id"] != second["run_id"]
    assert first["trace_path"] != second["trace_path"]


def test_missing_configuration_is_reported_without_starting_model(settings):
    def unavailable_factory(_settings, _trace):
        raise ModelUnavailable("尚未配置 DeepSeek 密钥。请填写本机 .env 后重试。")

    result = run_task("查询显热", settings, model_factory=unavailable_factory)
    assert result["status"] == "failed"
    assert "尚未配置" in result["answer"]
    assert result["calls"] == []


@pytest.mark.parametrize("batch_kind", ["business", "final_and_business", "multiple_final"])
def test_multiple_tool_calls_are_rejected_before_any_action_and_can_be_corrected(
    settings, batch_kind
):
    plan = {
        "steps": [
            {"step_id": "s1", "goal": "换算压力", "tool_name": "convert_units", "depends_on": []}
        ]
    }
    conversion = (
        "convert_units",
        {"step_id": "s1", "arguments": {"value": 1, "from_unit": "MPa", "to_unit": "kPa"}},
    )
    premature_final = (
        "final_answer",
        {"answer": "不应提交的答复。", "status": "needs_input", "citations": []},
    )
    batches = {
        "business": [("set_plan", plan), conversion],
        "final_and_business": [premature_final, ("set_plan", plan)],
        "multiple_final": [premature_final, premature_final],
    }
    model = ScriptedModel(
        [
            batches[batch_kind],
            ("set_plan", plan),
            conversion,
            (
                "final_answer",
                {"answer": "1 MPa = 1000 kPa。", "status": "completed", "citations": []},
            ),
        ]
    )
    progress = []
    result = run_task(
        "1 MPa 换算为 kPa。",
        settings,
        model_factory=lambda *_: model,
        on_progress=lambda value: progress.append(deepcopy(value)),
    )
    assert result["status"] == "completed"
    assert "1 MPa → 1000 kPa" in result["answer"]
    assert result["model_answer"] == "1 MPa = 1000 kPa。"
    assert result["answer_source"] == "verified_tools"
    assert len(model.received) == 4
    assert len(result["calls"]) == 1
    assert not progress[0]["plan"] and not progress[0]["calls"]
    assert progress[0]["status"] == "running"
    assert "每次回复只允许调用一个工具" in repr(model.received[1])


def test_finished_answer_survives_a_late_progress_callback_failure(settings):
    model = ScriptedModel(
        [
            (
                "final_answer",
                {"answer": "请补充比热。", "status": "needs_input", "citations": []},
            )
        ]
    )

    def broken_progress(_result):
        raise RuntimeError("subscriber failure")

    result = run_task(
        "给定流量求热负荷。",
        settings,
        model_factory=lambda *_: model,
        on_progress=broken_progress,
    )
    assert result["status"] == "needs_input"
    assert result["answer"] == "请补充比热。"
    assert len(model.received) == 1
    assert model.client.closed
