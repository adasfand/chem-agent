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
    persisted = json.loads(
        settings.runs_dir.joinpath(f"{result['run_id']}.json").read_text(encoding="utf-8")
    )
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


@pytest.mark.parametrize("batch_kind", ["final_and_business", "multiple_final"])
def test_unsafe_terminal_batches_are_rejected_before_any_action_and_can_be_corrected(
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
    assert "final_answer 必须单独调用" in repr(model.received[1])
    rejected = result["tool_batches"][0]
    assert rejected["status"] == "failed" and rejected["call_ids"] == []


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


@pytest.mark.parametrize(
    ("question", "history", "status"),
    [
        ("某液体1000 kg/h从25℃加热到65℃，请计算热负荷。", [], "needs_input"),
        (
            "某液体1000 kg/h从25℃加热到65℃，请计算热负荷。",
            [{"role": "assistant", "content": "默认比热4.18 kJ/(kg·K)。"}],
            "needs_input",
        ),
        (
            "某液体1000 kg/h从25℃加热到65℃，请计算热负荷。",
            [{"role": "user", "content": "比热4.18 kJ/(kg·K)。"}],
            "completed",
        ),
        ("1000 kg/h液体升温40K，比热4180 J/(kg·K)，求热负荷。", [], "completed"),
        (
            "1000 kg/h液体升温40K，比热改为2.5 kJ/(kg·K)，求热负荷。",
            [{"role": "user", "content": "比热4.18 kJ/(kg·K)。"}],
            "needs_input",
        ),
    ],
)
def test_agent_validates_user_capacity_before_calculating(settings, question, history, status):
    # The retrieved example must never count as user-supplied heat capacity.
    card = settings.knowledge_dir / "heat.md"
    card.write_text(
        card.read_text(encoding="utf-8") + "\n教学算例比热4.18 kJ/(kg·K)。\n", encoding="utf-8"
    )

    def factory(_settings, trace):
        def script(index):
            if index == 0:
                return "set_plan", {
                    "steps": [
                        {"step_id": "s1", "goal": "检索", "tool_name": "search_knowledge"},
                        {
                            "step_id": "s2",
                            "goal": "计算",
                            "tool_name": "calc_heat_duty",
                            "depends_on": ["s1"],
                        },
                    ]
                }
            if index == 1:
                return "search_knowledge", {"step_id": "s1", "arguments": {"query": "显热"}}
            if index == 2:
                return "calc_heat_duty", {
                    "step_id": "s2",
                    "arguments": {
                        "mass_flow_kg_s": 1000 / 3600,
                        "specific_heat_kj_kg_k": 4.18,
                        "delta_t_k": 40,
                    },
                }
            return "final_answer", {
                "answer": "已计算。" if status == "completed" else "请补充比热及单位。",
                "status": status,
                "citations": [trace.data["evidence"][0]["chunk_id"]],
            }

        return ScriptedModel(script)

    result = run_task(question, settings, history=history, model_factory=factory)
    assert result["status"] == status
    heat = result["calls"][-1]
    if status == "needs_input":
        assert heat["status"] == "failed" and "output" not in heat
        assert "不能使用教学算例" in heat["error"]
        assert "46.444" not in result["answer"]
    else:
        assert heat["status"] == "succeeded"
        assert heat["input_provenance"][0]["source"] == "user"
        assert heat["input_provenance"][0]["value"] == pytest.approx(4.18)
        assert "46.4444444444 kW" in result["answer"]


def test_model_can_submit_plan_and_multiple_independent_tools_in_one_batch(settings):
    plan = [
        {"step_id": "s1", "goal": "压力换算", "tool_name": "convert_units"},
        {"step_id": "s2", "goal": "温度换算", "tool_name": "convert_units"},
    ]
    model = ScriptedModel(
        [
            [
                ("set_plan", {"steps": plan}),
                (
                    "convert_units",
                    {
                        "step_id": "s1",
                        "arguments": {"value": 2.5, "from_unit": "MPa", "to_unit": "kPa"},
                    },
                ),
                (
                    "convert_units",
                    {
                        "step_id": "s2",
                        "arguments": {"value": 25, "from_unit": "degC", "to_unit": "K"},
                    },
                ),
            ],
            ("final_answer", {"answer": "已换算。", "status": "completed", "citations": []}),
        ]
    )
    result = run_task("换算2.5 MPa和25℃。", settings, model_factory=lambda *_: model)
    assert result["status"] == "completed"
    assert len(model.received) == 2
    assert [call["output"]["value"] for call in result["calls"]] == [2500, 298.15]
    assert "2500" in repr(model.received[1]) and "298.15" in repr(model.received[1])
    batch = result["tool_batches"][0]
    assert batch["tool_names"] == ["set_plan", "convert_units", "convert_units"]
    assert batch["agent_step"] == 1 and batch["model_request_index"] is None
    assert batch["execution_mode"] == "ordered" and batch["status"] == "succeeded"
    assert batch["call_ids"] == ["call_1", "call_2"]
    assert [call["batch_position"] for call in result["calls"]] == [2, 3]
    assert all(call["batch_id"] == batch["batch_id"] for call in result["calls"])


def test_invalid_plan_stops_remaining_batch_actions_and_keeps_first_error(settings):
    model = ScriptedModel(
        [
            [
                (
                    "set_plan",
                    {
                        "steps": [
                            {"step_id": "s2", "goal": "计算混合", "tool_name": "calc_mass_balance"}
                        ]
                    },
                ),
                ("search_knowledge", {"step_id": "s1", "arguments": {"query": "显热"}}),
                (
                    "calc_mass_balance",
                    {
                        "step_id": "s2",
                        "arguments": {"streams": [{"flow_kg_h": 500, "mass_fraction": 0.01}]},
                    },
                ),
            ],
            ("final_answer", {"answer": "执行计划需要补充。", "status": "failed", "citations": []}),
        ]
    )
    result = run_task("计算混合流量。", settings, model_factory=lambda *_: model)
    assert result["status"] == "failed"
    batch = result["tool_batches"][0]
    assert batch["status"] == "failed" and "计算计划需要先检索" in batch["error"]
    assert [a["status"] for a in batch["actions"]] == ["failed", "skipped", "skipped"]
    assert result["calls"] == [] and batch["call_ids"] == []
    assert '"status": "skipped"' in repr(model.received[1])
    assert "工具和步骤必须与已登记计划一致" not in repr(model.received[1])


@pytest.mark.parametrize("missing_search_dependency", [False, True])
def test_one_batch_reuses_real_search_mix_conversion_and_heat_outputs(
    settings, missing_search_dependency
):
    def factory(_settings, trace):
        plan = [
            {"step_id": "s1", "goal": "检索公式", "tool_name": "search_knowledge"},
            {
                "step_id": "s2",
                "goal": "混合",
                "tool_name": "calc_mass_balance",
                "depends_on": ["s1"],
            },
            {
                "step_id": "s3",
                "goal": "换算混合流量",
                "tool_name": "convert_units",
                "depends_on": ["s2"],
            },
            {
                "step_id": "s4",
                "goal": "计算热负荷",
                "tool_name": "calc_heat_duty",
                "depends_on": ["s1", "s3"],
            },
        ]
        if missing_search_dependency:
            plan[1]["depends_on"] = []

        def script(index):
            if index == 0:
                return [
                    ("set_plan", {"steps": plan}),
                    ("search_knowledge", {"step_id": "s1", "arguments": {"query": "显热热负荷"}}),
                    (
                        "calc_mass_balance",
                        {
                            "step_id": "s2",
                            "arguments": {
                                "streams": [
                                    {"flow_kg_h": 100, "mass_fraction": 0.05},
                                    {"flow_kg_h": 400, "mass_fraction": 0},
                                ]
                            },
                        },
                    ),
                    (
                        "convert_units",
                        {
                            "step_id": "s3",
                            "arguments": {
                                "value": {"$ref": "s2.total_flow_kg_h"},
                                "from_unit": "kg/h",
                                "to_unit": "kg/s",
                            },
                        },
                    ),
                    (
                        "calc_heat_duty",
                        {
                            "step_id": "s4",
                            "arguments": {
                                "mass_flow_kg_s": {"$ref": "s3.value"},
                                "specific_heat_kj_kg_k": 4.18,
                                "delta_t_k": 40,
                            },
                        },
                    ),
                ]
            return "final_answer", {
                "answer": "计算完成。",
                "status": "completed",
                "citations": [trace.data["evidence"][0]["chunk_id"]],
            }

        return ScriptedModel(script)

    result = run_task(
        "100和400 kg/h混合后升温40 K，比热4.18 kJ/(kg·K)。", settings, model_factory=factory
    )
    assert result["status"] == "completed"
    assert [call["status"] for call in result["calls"]] == ["succeeded"] * 4
    assert result["calls"][2]["input_refs"][0]["ref"] == "s2.total_flow_kg_h"
    assert result["calls"][3]["input_refs"][0]["ref"] == "s3.value"
    assert result["calls"][3]["output"]["heat_duty_kw"] == pytest.approx(500 / 3600 * 4.18 * 40)
    assert result["tool_batches"][0]["call_ids"] == ["call_1", "call_2", "call_3", "call_4"]
    actions = result["tool_batches"][0]["actions"]
    assert [a["status"] for a in actions] == ["succeeded"] * 5
    if missing_search_dependency:
        assert actions[0]["dependency_adjustments"] == [
            {"step_id": "s2", "depends_on_added": ["s1"]}
        ]
        assert result["plan"][1]["depends_on"] == ["s1"]


def test_failed_dependency_does_not_erase_independent_observations_and_can_be_retried(settings):
    plan = [
        {"step_id": "s1", "goal": "流量换算", "tool_name": "convert_units"},
        {"step_id": "s2", "goal": "回用流量", "tool_name": "convert_units", "depends_on": ["s1"]},
        {"step_id": "s3", "goal": "压力换算", "tool_name": "convert_units"},
    ]
    reference = (
        "convert_units",
        {
            "step_id": "s2",
            "arguments": {
                "value": {"$ref": "s1.value"},
                "from_unit": "kg/s",
                "to_unit": "kg/h",
            },
        },
    )
    model = ScriptedModel(
        [
            [
                ("set_plan", {"steps": plan}),
                (
                    "convert_units",
                    {
                        "step_id": "s1",
                        "arguments": {"value": 3600, "from_unit": "kg/h", "to_unit": "kPa"},
                    },
                ),
                reference,
                (
                    "convert_units",
                    {
                        "step_id": "s3",
                        "arguments": {"value": 2, "from_unit": "MPa", "to_unit": "kPa"},
                    },
                ),
            ],
            [
                (
                    "convert_units",
                    {
                        "step_id": "s1",
                        "arguments": {"value": 3600, "from_unit": "kg/h", "to_unit": "kg/s"},
                    },
                ),
                reference,
            ],
            ("final_answer", {"answer": "已换算。", "status": "completed", "citations": []}),
        ]
    )
    result = run_task("换算流量与压力。", settings, model_factory=lambda *_: model)
    assert result["status"] == "completed"
    assert [call["status"] for call in result["calls"]] == [
        "failed",
        "failed",
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    assert "前序步骤未成功" in result["calls"][1]["error"]
    assert "output" not in result["calls"][0] and "output" not in result["calls"][1]
    assert "量纲" in repr(model.received[1]) and "前序步骤未成功" in repr(model.received[1])
    assert "2000" in repr(model.received[1])
    assert result["tool_batches"][0]["status"] == "failed"
    assert result["tool_batches"][1]["status"] == "succeeded"


def test_cancel_between_batch_actions_keeps_first_result_and_never_runs_second(settings):
    import threading

    cancel = threading.Event()
    model = ScriptedModel(
        [
            [
                (
                    "set_plan",
                    {
                        "steps": [
                            {"step_id": "s1", "goal": "压力换算", "tool_name": "convert_units"},
                            {"step_id": "s2", "goal": "另一次换算", "tool_name": "convert_units"},
                        ]
                    },
                ),
                (
                    "convert_units",
                    {
                        "step_id": "s1",
                        "arguments": {"value": 1, "from_unit": "MPa", "to_unit": "kPa"},
                    },
                ),
                (
                    "convert_units",
                    {
                        "step_id": "s2",
                        "arguments": {"value": 2, "from_unit": "MPa", "to_unit": "kPa"},
                    },
                ),
            ]
        ]
    )

    def progress(result):
        if result["calls"]:
            cancel.set()

    result = run_task(
        "换算压力。",
        settings,
        model_factory=lambda *_: model,
        cancel_event=cancel,
        on_progress=progress,
    )
    assert result["status"] == "cancelled"
    assert len(result["calls"]) == 1 and result["calls"][0]["output"]["value"] == 1000
    assert result["plan"][1]["status"] == "pending"
    assert result["tool_batches"][0]["status"] == "cancelled"
    assert result["tool_batches"][0]["call_ids"] == ["call_1"]


@pytest.mark.parametrize("order", ["late", "duplicate"])
def test_plan_must_be_unique_first_action_before_any_batch_side_effect(settings, order):
    plan = (
        "set_plan",
        {"steps": [{"step_id": "s1", "goal": "换算压力", "tool_name": "convert_units"}]},
    )
    conversion = (
        "convert_units",
        {"step_id": "s1", "arguments": {"value": 1, "from_unit": "MPa", "to_unit": "kPa"}},
    )
    batch = [conversion, plan] if order == "late" else [plan, plan, conversion]
    model = ScriptedModel(
        [
            batch,
            ("final_answer", {"answer": "请确认单位。", "status": "needs_input", "citations": []}),
        ]
    )
    result = run_task("换算压力。", settings, model_factory=lambda *_: model)
    assert result["status"] == "needs_input" and result["plan"] == [] and result["calls"] == []
    assert result["tool_batches"][0]["status"] == "failed"
    assert "set_plan 必须" in repr(model.received[1])


def test_batch_links_to_one_based_recorded_model_requests(settings):
    def factory(_settings, trace):
        class RecordedModel(ScriptedModel):
            def generate(self, *args, **kwargs):
                response = super().generate(*args, **kwargs)
                trace.data["model_requests"].append(
                    {
                        "status": "succeeded",
                        "selected_tools": [call.function.name for call in response.tool_calls],
                    }
                )
                return response

        return RecordedModel(
            [
                [
                    (
                        "set_plan",
                        {
                            "steps": [
                                {"step_id": "s1", "goal": "换算压力", "tool_name": "convert_units"}
                            ]
                        },
                    ),
                    (
                        "convert_units",
                        {
                            "step_id": "s1",
                            "arguments": {"value": 1, "from_unit": "MPa", "to_unit": "kPa"},
                        },
                    ),
                ],
                ("final_answer", {"answer": "完成。", "status": "completed", "citations": []}),
            ]
        )

    result = run_task("换算压力。", settings, model_factory=factory)
    assert result["status"] == "completed"
    assert [batch["model_request_index"] for batch in result["tool_batches"]] == [1, 2]
    for batch in result["tool_batches"]:
        assert (
            batch["tool_names"]
            == result["model_requests"][batch["model_request_index"] - 1]["selected_tools"]
        )


def test_duplicate_response_ids_are_rejected_before_plan_registration(settings):
    class DuplicateModel(ScriptedModel):
        def generate(self, *args, **kwargs):
            response = super().generate(*args, **kwargs)
            if len(self.received) == 1:
                response.tool_calls[1].id = response.tool_calls[0].id
            return response

    model = DuplicateModel(
        [
            [
                (
                    "set_plan",
                    {
                        "steps": [
                            {"step_id": "s1", "goal": "换算压力", "tool_name": "convert_units"}
                        ]
                    },
                ),
                (
                    "convert_units",
                    {
                        "step_id": "s1",
                        "arguments": {"value": 1, "from_unit": "MPa", "to_unit": "kPa"},
                    },
                ),
            ],
            ("final_answer", {"answer": "请确认单位。", "status": "needs_input", "citations": []}),
        ]
    )
    result = run_task("换算压力。", settings, model_factory=lambda *_: model)
    assert result["status"] == "needs_input" and result["plan"] == [] and result["calls"] == []
    assert "编号不能重复" in result["tool_batches"][0]["error"]


def test_cancel_wrapped_by_framework_never_becomes_a_retry_observation(settings, monkeypatch):
    import threading

    from chem_agent.tools import BusinessTool

    cancel = threading.Event()
    original = BusinessTool.forward

    def cancelling_forward(self, step_id: str, arguments: dict) -> dict:
        cancel.set()
        return original(self, step_id, arguments)

    monkeypatch.setattr(BusinessTool, "forward", cancelling_forward)
    model = ScriptedModel(
        [
            [
                (
                    "set_plan",
                    {
                        "steps": [
                            {"step_id": "s1", "goal": "换算压力", "tool_name": "convert_units"}
                        ]
                    },
                ),
                (
                    "convert_units",
                    {
                        "step_id": "s1",
                        "arguments": {"value": 1, "from_unit": "MPa", "to_unit": "kPa"},
                    },
                ),
            ]
        ]
    )
    result = run_task("换算压力。", settings, model_factory=lambda *_: model, cancel_event=cancel)
    assert result["status"] == "cancelled" and result["calls"] == []
    assert result["tool_batches"][0]["status"] == "cancelled" and len(model.received) == 1


def test_final_validation_failure_returns_the_actionable_reason_for_retry(settings):
    model = ScriptedModel(
        [
            ("final_answer", {"answer": "完成。", "status": "completed", "citations": []}),
            ("final_answer", {"answer": "请补充条件。", "status": "needs_input", "citations": []}),
        ]
    )
    result = run_task("计算热负荷。", settings, model_factory=lambda *_: model)
    assert result["status"] == "needs_input"
    assert "计划尚未全部成功" in repr(model.received[1])
    assert result["tool_batches"][0]["status"] == "failed"


def test_unexpected_business_failure_is_sanitized_and_later_action_still_observed(
    settings, monkeypatch
):
    from chem_agent.execution import Execution

    original = Execution.__init__

    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        actual = self.functions["convert_units"]

        def convert(**arguments):
            if arguments["value"] == 1:
                raise RuntimeError("provider-private-payload offline-dummy-key")
            return actual(**arguments)

        self.functions["convert_units"] = convert

    monkeypatch.setattr(Execution, "__init__", init)
    model = ScriptedModel(
        [
            [
                (
                    "set_plan",
                    {
                        "steps": [
                            {"step_id": "s1", "goal": "换算压力", "tool_name": "convert_units"},
                            {"step_id": "s2", "goal": "另一换算", "tool_name": "convert_units"},
                        ]
                    },
                ),
                (
                    "convert_units",
                    {
                        "step_id": "s1",
                        "arguments": {"value": 1, "from_unit": "MPa", "to_unit": "kPa"},
                    },
                ),
                (
                    "convert_units",
                    {
                        "step_id": "s2",
                        "arguments": {"value": 2, "from_unit": "MPa", "to_unit": "kPa"},
                    },
                ),
            ],
            ("final_answer", {"answer": "请稍后重试。", "status": "failed", "citations": []}),
        ]
    )
    result = run_task("换算压力。", settings, model_factory=lambda *_: model)
    assert [call["status"] for call in result["calls"]] == ["failed", "succeeded"]
    assert "2000" in repr(model.received[1]) and "工具执行失败" in repr(model.received[1])
    assert "provider-private-payload" not in json.dumps(result, ensure_ascii=False)
    assert settings.api_key not in json.dumps(result, ensure_ascii=False)
