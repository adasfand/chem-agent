"""Acceptance assertions reject misleading traces without using a provider."""

import json
from copy import deepcopy

import pytest

from chem_agent.config import Settings
from chem_agent.execution import Execution
from chem_agent.knowledge import KnowledgeBase
from chem_agent.trace import RunTrace
from scripts import validate_live as validation

HEAT_ANSWER = "热负荷约46.44 kW。按稳态、单相、恒比热、无化学反应、无相变、忽略热损失计算。"
BALANCE_ANSWER = "混合总流量500 kg/h，盐质量分数1%。稳态、无反应、无积累、无泄漏、充分混合。"


def call(step, tool, arguments, output, refs=None, requested=None):
    return {
        "step_id": step,
        "tool_name": tool,
        "status": "succeeded",
        "arguments": arguments,
        "requested_arguments": requested if requested is not None else deepcopy(arguments),
        "output": output,
        "input_refs": refs or [],
    }


def result_with_evidence():
    hit = {"chunk_id": "heat:formula", "text": "# 显热\n稳态单相恒比热。"}
    search = call(
        "s1",
        "search_knowledge",
        {"query": "显热"},
        {
            "hits": [hit],
            "retrieval": {"metadata": {"backend": "lexical"}},
        },
    )
    return {
        "run_id": "offline-acceptance",
        "status": "completed",
        "answer": HEAT_ANSWER,
        "calls": [search],
        "plan": [{"step_id": "s1", "depends_on": []}],
        "evidence": [hit],
        "citations": [hit["chunk_id"]],
        "model_requests": [{"messages": [{"role": "user", "content": str(search["output"])}]}],
    }


@pytest.fixture
def heat_result():
    result = result_with_evidence()
    flow = 1000 / 3600
    result["plan"].extend(
        [
            {"step_id": "s2", "depends_on": []},
            {"step_id": "s3", "depends_on": ["s1", "s2"]},
        ]
    )
    result["calls"].extend(
        [
            call(
                "s2",
                "convert_units",
                {"value": 1000, "from_unit": "kg/h", "to_unit": "kg/s"},
                {"value": flow, "unit": "kg/s"},
            ),
            call(
                "s3",
                "calc_heat_duty",
                {"mass_flow_kg_s": flow, "specific_heat_kj_kg_k": 4.18, "delta_t_k": 40},
                {"heat_duty_kw": flow * 4.18 * 40},
                refs=[
                    {
                        "argument": "mass_flow_kg_s",
                        "ref": "s2.value",
                        "source_value": flow,
                        "source_unit": "kg/s",
                        "value": flow,
                        "unit": "kg/s",
                    }
                ],
                requested={
                    "mass_flow_kg_s": {"$ref": "s2.value"},
                    "specific_heat_kj_kg_k": 4.18,
                    "delta_t_k": 40,
                },
            ),
        ]
    )
    return result


@pytest.fixture
def mixed_result():
    result = result_with_evidence()
    result["answer"] = BALANCE_ANSWER + HEAT_ANSWER.replace("46.44", "23.2222222222")
    streams = [
        {"flow_kg_h": 100, "mass_fraction": 0.05},
        {"flow_kg_h": 400, "mass_fraction": 0},
    ]
    result["plan"].extend(
        [
            {"step_id": "s2", "depends_on": ["s1"]},
            {"step_id": "s3", "depends_on": ["s2"]},
            {"step_id": "s4", "depends_on": ["s1", "s2", "s3"]},
        ]
    )
    flow = 500 / 3600
    result["calls"].extend(
        [
            call(
                "s2",
                "calc_mass_balance",
                {"streams": streams},
                {"total_flow_kg_h": 500, "component_flow_kg_h": 5, "mass_fraction": 0.01},
            ),
            call(
                "s3",
                "convert_units",
                {"value": 500, "from_unit": "kg/h", "to_unit": "kg/s"},
                {"value": flow, "unit": "kg/s"},
                refs=[
                    {
                        "argument": "value",
                        "ref": "s2.total_flow_kg_h",
                        "source_value": 500,
                        "source_unit": "kg/h",
                        "value": 500,
                        "unit": "kg/h",
                    }
                ],
                requested={
                    "value": {"$ref": "s2.total_flow_kg_h"},
                    "from_unit": "kg/h",
                    "to_unit": "kg/s",
                },
            ),
            call(
                "s4",
                "calc_heat_duty",
                {"mass_flow_kg_s": flow, "specific_heat_kj_kg_k": 4.18, "delta_t_k": 40},
                {"heat_duty_kw": flow * 4.18 * 40},
                refs=[
                    {
                        "argument": "mass_flow_kg_s",
                        "ref": "s3.value",
                        "source_value": flow,
                        "source_unit": "kg/s",
                        "value": flow,
                        "unit": "kg/s",
                    }
                ],
                requested={
                    "mass_flow_kg_s": {"$ref": "s3.value"},
                    "specific_heat_kj_kg_k": 4.18,
                    "delta_t_k": 40,
                },
            ),
        ]
    )
    return result


def test_complete_heat_and_real_mixed_chain_pass(heat_result, mixed_result):
    validation.check_heat(heat_result, 1000 / 3600 * 4.18 * 40)
    validation.mixed_heat_check(mixed_result)
    assert validation.check_backend(heat_result, "lexical") == ["lexical"]


def test_actual_mixed_execution_and_canonical_answer_satisfy_acceptance(projects):
    current, _indexed = projects
    knowledge = KnowledgeBase(current / "data" / "knowledge")
    trace = RunTrace(current / "runs", "离线混合显热验收", {}, knowledge.version, mode="offline")
    execution = Execution(knowledge, trace)
    execution.set_plan(
        [
            {"step_id": "s1", "goal": "检索", "tool_name": "search_knowledge"},
            {
                "step_id": "s2",
                "goal": "混合",
                "tool_name": "calc_mass_balance",
                "depends_on": ["s1"],
            },
            {"step_id": "s3", "goal": "换算", "tool_name": "convert_units", "depends_on": ["s2"]},
            {
                "step_id": "s4",
                "goal": "加热",
                "tool_name": "calc_heat_duty",
                "depends_on": ["s1", "s2", "s3"],
            },
        ]
    )
    found = execution.execute("search_knowledge", "s1", {"query": "显热"})["output"]
    execution.execute(
        "calc_mass_balance",
        "s2",
        {
            "streams": [
                {"flow_kg_h": 100, "mass_fraction": 0.05},
                {"flow_kg_h": 400, "mass_fraction": 0},
            ]
        },
    )
    execution.execute(
        "convert_units",
        "s3",
        {"value": {"$ref": "s2.total_flow_kg_h"}, "from_unit": "kg/h", "to_unit": "kg/s"},
    )
    execution.execute(
        "calc_heat_duty",
        "s4",
        {"mass_flow_kg_s": {"$ref": "s3.value"}, "specific_heat_kj_kg_k": 4.18, "delta_t_k": 40},
    )
    trace.data["model_requests"] = [{"messages": [{"role": "user", "content": str(found)}]}]
    execution.complete(
        "模型错误说明9999 kW。", "completed", [hit["chunk_id"] for hit in found["hits"]]
    )
    result = trace.result()
    validation.mixed_heat_check(result)
    assert result["answer_source"] == "verified_tools"
    assert "9999" not in result["answer"] and "9999" in result["model_answer"]


@pytest.mark.parametrize(
    "missing", ["稳态", "单相", "恒比热", "无化学反应", "无相变", "忽略热损失"]
)
def test_correct_tool_number_does_not_hide_a_missing_answer_condition(heat_result, missing):
    heat_result["answer"] = HEAT_ANSWER.replace(missing, "")
    with pytest.raises(AssertionError, match="前提"):
        validation.check_heat(heat_result, 1000 / 3600 * 4.18 * 40)


@pytest.mark.parametrize(
    "answer", [HEAT_ANSWER.replace("46.44", "9999"), HEAT_ANSWER.replace("kW", "kJ")]
)
def test_correct_tool_number_does_not_hide_a_wrong_answer_value_or_unit(heat_result, answer):
    heat_result["answer"] = answer
    with pytest.raises(AssertionError, match="数值"):
        validation.check_heat(heat_result, 1000 / 3600 * 4.18 * 40)


def test_temperature_reference_cannot_stand_in_for_mass_flow_reference(heat_result):
    heat = heat_result["calls"][-1]
    heat["requested_arguments"]["mass_flow_kg_s"] = 1000 / 3600
    heat["input_refs"][0]["argument"] = "delta_t_k"
    with pytest.raises(AssertionError, match="真实"):
        validation.check_heat(heat_result, 1000 / 3600 * 4.18 * 40)


@pytest.mark.parametrize(
    "field,value", [("ref", "s8.value"), ("source_value", 0.5), ("unit", "g/s")]
)
def test_requested_reference_and_resolution_must_match_real_source(heat_result, field, value):
    heat_result["calls"][-1]["input_refs"][0][field] = value
    with pytest.raises(AssertionError, match="引用"):
        validation.check_heat(heat_result, 1000 / 3600 * 4.18 * 40)


def test_undeclared_or_failed_reference_is_rejected(heat_result):
    heat_result["plan"][-1]["depends_on"] = ["s1"]
    with pytest.raises(AssertionError, match="依赖"):
        validation.check_heat(heat_result, 1000 / 3600 * 4.18 * 40)
    heat_result["plan"][-1]["depends_on"] = ["s1", "s2"]
    heat_result["calls"][1]["status"] = "failed"
    with pytest.raises(AssertionError, match="先成功"):
        validation.check_heat(heat_result, 1000 / 3600 * 4.18 * 40)


def test_mixed_chain_rejects_copied_total_flow(mixed_result):
    mixed_result["calls"][2]["requested_arguments"]["value"] = 500
    with pytest.raises(AssertionError, match="真实"):
        validation.mixed_heat_check(mixed_result)


@pytest.mark.parametrize("missing", ["稳态", "无反应", "无积累", "无泄漏", "充分混合"])
def test_balance_answer_requires_all_mixing_conditions(mixed_result, missing):
    mixed_result["answer"] = BALANCE_ANSWER.replace(missing, "")
    with pytest.raises(AssertionError, match="前提"):
        validation.balance_check(mixed_result)


def test_each_cited_excerpt_must_be_in_observed_model_context(heat_result):
    extra = {"chunk_id": "unseen:formula", "text": "# 没有进入上下文的来源"}
    heat_result["evidence"].append(extra)
    heat_result["citations"].append(extra["chunk_id"])
    with pytest.raises(AssertionError, match="原文"):
        validation.knowledge_check(heat_result)


@pytest.mark.parametrize("serialize", [str, lambda value: json.dumps(value, ensure_ascii=False)])
def test_full_quoted_multiline_excerpt_is_checked_through_observation_encoding(
    heat_result, serialize
):
    hit = heat_result["evidence"][0]
    hit["text"] = "# 引用\n说明 \"功率\" 与 '热量' 的区别。"
    heat_result["model_requests"] = [
        {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": serialize({"hits": [hit]})}]}
            ]
        }
    ]
    validation.knowledge_check(heat_result)


@pytest.fixture
def temperature_result():
    result = result_with_evidence()
    explanation = "绝对温度带有温标原点；温差表示两个状态的差，因此换算温差时不添加温标偏移。"
    result["answer"] = "计算结果：\n- 单位换算：25 degC → 298.15 K。\n\n补充说明：\n" + explanation
    result["plan"].append({"step_id": "s2", "depends_on": []})
    result["calls"].append(
        call(
            "s2",
            "convert_units",
            {"value": 25, "from_unit": "degC", "to_unit": "K"},
            {"value": 298.15, "unit": "K", "from_value": 25, "from_unit": "degC"},
        )
    )
    return result


def test_compound_temperature_case_requires_and_accepts_preserved_explanation(temperature_result):
    validation.temperature_explanation_check(temperature_result)


@pytest.mark.parametrize(
    "explanation",
    ["", "补充说明：绝对温度与温差不同。", "补充说明：绝对温度需要偏移，温差不添加偏移。"],
)
def test_compound_temperature_case_rejects_numeric_only_or_incomplete_explanation(
    temperature_result, explanation
):
    temperature_result["answer"] = "25 degC → 298.15 K。\n" + explanation
    with pytest.raises(AssertionError):
        validation.temperature_explanation_check(temperature_result)


def test_compound_temperature_case_can_use_a_preserved_full_source_quote(temperature_result):
    quote = "绝对温度换算有原点偏移；温差是两个温度的差值，温差换算不加273.15。"
    hit = temperature_result["evidence"][0]
    hit["text"] = "# 温差与绝对温度\n" + quote
    temperature_result["model_requests"] = [
        {"messages": [{"role": "user", "content": str({"hits": [hit]})}]}
    ]
    temperature_result["answer"] = (
        "25 degC → 298.15 K。\n来源原文（heat:formula；非本轮计算结果）：\n> " + quote
    )
    validation.temperature_explanation_check(temperature_result)


def test_compound_temperature_case_checks_the_actual_conversion_value(temperature_result):
    temperature_result["calls"][-1]["output"]["value"] = 299.15
    with pytest.raises(AssertionError, match="换算结果"):
        validation.temperature_explanation_check(temperature_result)


def test_recovered_attempts_are_counted_once_despite_repeated_request_history(heat_result):
    error = {"role": "user", "content": validation._BATCH_ERROR}
    context = heat_result["model_requests"][0]["messages"]
    heat_result["model_requests"] = [
        {"messages": context + [error]},
        {"messages": context + [error]},
        {"messages": context + [error, error]},
        {"messages": context + [error, error]},
    ]
    failed = deepcopy(heat_result["calls"][1])
    failed["status"] = "failed"
    heat_result["calls"].insert(0, failed)
    summary = validation.recovery_summary(heat_result)
    assert summary["blocked_tool_batches"] == 2
    assert summary["failed_tool_calls"] == 1
    assert summary["recovered"] is True
    validation.check_heat(heat_result, 1000 / 3600 * 4.18 * 40)


def test_final_answer_rejection_and_retry_is_counted_once_from_text_blocks(heat_result):
    context = heat_result["model_requests"][0]["messages"]
    error = {
        "role": "user",
        "content": [{"type": "text", "text": "Error executing tool 'final_answer': 错误说明"}],
    }
    heat_result["model_requests"] = [{"messages": context + [error]} for _ in range(3)]
    summary = validation.recovery_summary(heat_result)
    assert summary["failed_final_answers"] == 1
    assert summary["blocked_tool_batches"] == 0 and summary["failed_tool_calls"] == 0
    assert summary["recovered"] is True
    validation.check_heat(heat_result, 1000 / 3600 * 4.18 * 40)


def test_ready_backend_is_not_silently_treated_as_lexical(heat_result):
    with pytest.raises(AssertionError, match="后端"):
        validation.check_backend(heat_result, "lightrag")


def test_code_identity_tracks_evaluated_source_without_private_files(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    public = source / "public.py"
    public.write_text("VALUE = 1\n")
    private = tmp_path / ".env"
    private.write_text("PRIVATE_TEST_VALUE=one\n")
    initial = validation.code_identity(tmp_path)
    private.write_text("PRIVATE_TEST_VALUE=two\n")
    assert validation.code_identity(tmp_path)["source_sha256"] == initial["source_sha256"]
    public.write_text("VALUE = 2\n")
    changed = validation.code_identity(tmp_path)
    assert changed["source_sha256"] != initial["source_sha256"]
    assert changed["files"] == 1 and changed["commit"] is None


@pytest.fixture
def projects(tmp_path):
    current = tmp_path / "current"
    indexed = tmp_path / "indexed"
    for root in (current, indexed):
        knowledge = root / "data" / "knowledge"
        knowledge.mkdir(parents=True)
        (knowledge / "heat.md").write_text("# 显热\n来源：测试\n\n稳态恒比热。")
    return current, indexed


def test_external_index_keeps_current_knowledge_runs_and_provider_configuration(
    projects, monkeypatch
):
    current, indexed = projects
    state = {"state": "ready", "backend": "lightrag"}

    class ReadyRetriever:
        def __init__(self, settings):
            self.index_status = state
            assert settings.root == indexed
            assert settings.knowledge_dir == current / "data" / "knowledge"
            assert settings.runs_dir == current / "runs"

    monkeypatch.setattr(validation, "HybridRetriever", ReadyRetriever)
    configured = Settings(root=current, api_key="offline-only", model="current-model", max_steps=14)
    settings, actual = validation.prepare_settings(configured, indexed, "lightrag")
    assert actual == state and settings.model == "current-model" and settings.max_steps == 14
    assert settings.api_key == "offline-only"
    assert not (indexed / "runs").exists()


def test_wrong_external_knowledge_is_rejected_before_retriever_or_model(projects, monkeypatch):
    current, indexed = projects
    (indexed / "data" / "knowledge" / "heat.md").write_text("# 完全不同的资料")
    monkeypatch.setattr(validation, "HybridRetriever", lambda *_: pytest.fail("not matching"))
    with pytest.raises(ValueError, match="知识版本"):
        validation.prepare_settings(Settings(root=current), indexed, "lightrag")


@pytest.mark.parametrize("backend,state", [("lightrag", "missing"), ("lexical", "ready")])
def test_backend_preflight_fails_without_calling_models(projects, monkeypatch, backend, state):
    current, _indexed = projects

    class Retriever:
        def __init__(self, _settings):
            self.index_status = {"state": state}

    monkeypatch.setattr(validation, "HybridRetriever", Retriever)
    with pytest.raises(ValueError):
        validation.prepare_settings(Settings(root=current), backend=backend)


def test_main_preserves_original_cases_adds_mixed_case_and_reports_recovery(
    tmp_path, monkeypatch, heat_result, mixed_result, capsys
):
    project = tmp_path / "project"
    (project / "examples").mkdir(parents=True)
    (project / "examples" / "tasks.json").write_text(
        json.dumps(
            [
                {"id": name, "question": name}
                for name in ("knowledge", "heat", "balance", "units", "missing")
            ]
        )
    )
    monkeypatch.setattr(validation, "ROOT", project)
    settings = validation.EvaluationSettings(root=project, project_root=project)
    monkeypatch.setattr(validation.Settings, "load", lambda _root: settings)
    monkeypatch.setattr(validation, "prepare_settings", lambda *_: (settings, {"state": "missing"}))
    # Other tests exercise each assertion independently. Here observe dispatch,
    # history propagation and summary persistence with a deterministic runner.
    for name in (
        "knowledge_check",
        "check_heat",
        "balance_check",
        "unit_check",
        "missing_check",
        "invalid_check",
        "mixed_heat_check",
        "temperature_explanation_check",
    ):
        monkeypatch.setattr(validation, name, lambda *_: None)
    calls = []

    def runner(question, _settings, history=None):
        calls.append((question, history))
        result = deepcopy(mixed_result if len(calls) == 9 else heat_result)
        result["run_id"] = f"offline-{len(calls)}"
        if len(calls) == 6:
            result.update(status="needs_input", answer="请补充比热。")
        if len(calls) == 8:
            result["status"] = "out_of_scope"
        return result

    monkeypatch.setattr(validation, "run_task", runner)
    with pytest.raises(SystemExit) as exited:
        validation.main([])
    assert exited.value.code == 0
    report = json.loads((project / "runs" / "live_validation.json").read_text())
    assert [case["case"] for case in report["cases"]] == [
        "knowledge",
        "heat",
        "heat_changed_input",
        "balance",
        "units",
        "missing_parameter",
        "follow_up",
        "incompatible_units",
        "mixed_heat",
        "temperature_explanation",
    ]
    assert len(calls) == 10 and report["passed"] is True
    assert calls[6][1] == [
        {"role": "user", "content": "missing"},
        {"role": "assistant", "content": "请补充比热。"},
    ]
    assert all("recovery" in case for case in report["cases"])
    assert "offline-10" in capsys.readouterr().out
