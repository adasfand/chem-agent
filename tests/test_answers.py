"""User-visible numeric answers cannot inherit model rounding or missing conditions."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from chem_agent.execution import Execution
from chem_agent.knowledge import KnowledgeBase
from chem_agent.report import render_report
from chem_agent.tools import FinalTool
from chem_agent.trace import RunTrace

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def execution(tmp_path):
    knowledge = KnowledgeBase(ROOT / "data" / "knowledge")
    return Execution(knowledge, RunTrace(tmp_path, "计算任务", {}, knowledge.version))


def heat(execution, flow=1000, capacity=4.18, delta=40):
    execution.set_plan(
        [
            {"step_id": "s1", "goal": "换算流量", "tool_name": "convert_units"},
            {
                "step_id": "s2",
                "goal": "计算显热",
                "tool_name": "calc_heat_duty",
                "depends_on": ["s1"],
            },
        ]
    )
    execution.execute(
        "convert_units", "s1", {"value": flow, "from_unit": "kg/h", "to_unit": "kg/s"}
    )
    execution.execute(
        "calc_heat_duty",
        "s2",
        {
            "mass_flow_kg_s": {"$ref": "s1.value"},
            "specific_heat_kj_kg_k": capacity,
            "delta_t_k": delta,
        },
    )


@pytest.mark.parametrize("flow", [1000, 2000])
def test_completed_heat_replaces_wrong_model_arithmetic_and_keeps_unrounded_trace(execution, flow):
    heat(execution, flow)
    calls = deepcopy(execution.trace.data["calls"])
    model_answer = "0.2778 × 4.18 × 40 = 999 kW。"
    answer = execution.complete(model_answer, "completed", [])
    expected = flow / 3600 * 4.18 * 40
    assert f"{expected:.12g} kW" in answer
    assert "999" not in answer and "0.2778 ×" not in answer
    assert "使用未舍入的输入计算" in answer
    for condition in (
        "单相",
        "稳态",
        "恒比热",
        "无化学反应",
        "无相变",
        "忽略热损失",
        "轴功",
        "动能",
        "位能",
    ):
        assert condition in answer
    assert execution.trace.data["calls"] == calls
    persisted = json.loads(execution.trace.path.read_text())
    assert persisted["answer"] == answer
    assert persisted["model_answer"] == model_answer
    assert persisted["answer_source"] == "verified_tools"
    assert persisted["calls"][-1]["arguments"]["mass_flow_kg_s"] == flow / 3600
    report = render_report(persisted)
    assert answer in report and model_answer not in report


@pytest.mark.parametrize(("flow", "delta", "label"), [(2000, -5, "冷却"), (0, 40, "零热负荷")])
def test_answer_uses_changed_inputs_and_does_not_default_to_teaching_values(
    execution, flow, delta, label
):
    heat(execution, flow, capacity=2.5, delta=delta)
    answer = execution.complete("热负荷46.44 kW。", "completed", [])
    assert f"{flow / 3600 * 2.5 * delta:.12g} kW（{label}）" in answer
    assert "比热 2.5 kJ/(kg·K)" in answer
    assert f"温差 {delta} K" in answer
    assert "46.44" not in answer and "4.18" not in answer


def test_mixed_heat_answer_includes_both_calculations_and_successful_reference_chain(execution):
    execution.set_plan(
        [
            {"step_id": "s1", "goal": "混合", "tool_name": "calc_mass_balance"},
            {"step_id": "s2", "goal": "换算", "tool_name": "convert_units", "depends_on": ["s1"]},
            {"step_id": "s3", "goal": "加热", "tool_name": "calc_heat_duty", "depends_on": ["s2"]},
        ]
    )
    execution.execute(
        "calc_mass_balance",
        "s1",
        {
            "streams": [
                {"flow_kg_h": 100, "mass_fraction": 0.05},
                {"flow_kg_h": 400, "mass_fraction": 0},
            ]
        },
    )
    with pytest.raises(ValueError, match="字段不存在"):
        execution.execute(
            "convert_units",
            "s2",
            {"value": {"$ref": "s1.value"}, "from_unit": "kg/h", "to_unit": "kg/s"},
        )
    execution.execute(
        "convert_units",
        "s2",
        {"value": {"$ref": "s1.total_flow_kg_h"}, "from_unit": "kg/h", "to_unit": "kg/s"},
    )
    execution.execute(
        "calc_heat_duty",
        "s3",
        {"mass_flow_kg_s": {"$ref": "s2.value"}, "specific_heat_kj_kg_k": 4.18, "delta_t_k": 40},
    )
    answer = execution.complete("500 kg/h，0.1389 × 4.18 × 40 = 23.22 kW。", "completed", [])
    assert "混合后总流量：500 kg/h" in answer
    assert "目标组分质量流量：5 kg/h" in answer
    assert "目标组分质量分数：0.01（1%）" in answer
    assert "23.2222222222 kW" in answer
    assert "0.1389 ×" not in answer
    for condition in ("稳态", "完全混合", "无反应", "无泄漏", "无积累", "同一守恒组分"):
        assert condition in answer
    assert execution.trace.data["calls"][-1]["input_refs"][0]["ref"] == "s2.value"


def test_unit_answer_preserves_offset_temperature_conversion_without_model_fabrication(execution):
    execution.set_plan([{"step_id": "s1", "goal": "换算温度", "tool_name": "convert_units"}])
    execution.execute("convert_units", "s1", {"value": 32, "from_unit": "degF", "to_unit": "degC"})
    answer = execution.complete("32 degF = 320 degC", "completed", [])
    displayed = re.search(r"32 degF → ([\deE.+-]+) degC", answer)
    assert displayed and float(displayed[1]) == pytest.approx(0, abs=1e-10)
    assert "320" not in answer
    assert "适用条件" not in answer


def test_knowledge_only_answer_and_citations_remain_the_model_response(execution):
    execution.set_plan([{"step_id": "s1", "goal": "检索", "tool_name": "search_knowledge"}])
    result = execution.execute("search_knowledge", "s1", {"query": "显热公式适用条件"})
    citations = [result["output"]["hits"][0]["chunk_id"]]
    answer = "显热公式 Q = m × cp × ΔT，假设单相恒比热。"
    assert execution.complete(answer, "completed", citations) == answer
    assert execution.trace.data["citations"] == citations
    assert "model_answer" not in execution.trace.data
    assert "answer_source" not in execution.trace.data


def test_compound_unit_question_preserves_its_concept_explanation(execution):
    execution.set_plan(
        [
            {"step_id": "s1", "goal": "查温标区别", "tool_name": "search_knowledge"},
            {"step_id": "s2", "goal": "换算温度", "tool_name": "convert_units"},
        ]
    )
    found = execution.execute("search_knowledge", "s1", {"query": "绝对温度 温差 区别"})
    execution.execute("convert_units", "s2", {"value": 25, "from_unit": "degC", "to_unit": "K"})
    citation = found["output"]["hits"][0]["chunk_id"]
    explanation = "绝对温度带有温标原点；温差表示两个状态的差，因此换算温差时不添加温标偏移。"
    answer = FinalTool(execution).forward("25℃转换成功。", "completed", [citation], explanation)
    assert "25 degC → 298.15 K" in answer
    assert explanation in answer and "补充说明" in answer
    assert execution.trace.data["model_explanation"] == explanation
    assert execution.trace.data["answer_source"] == "verified_tools_with_explanation"


@pytest.mark.parametrize(
    "explanation",
    [
        "0.2778 × 4.18 × 40 = 46.44 kW",
        "热负荷为999 kW。",
        "0.2778⋅4.18⋅40",
        "热负荷为999千瓦。",
        "热负荷为999 KW。",
        "目标组分质量分数为0.9。",
        "热负荷为９９９ＫＷ。",
    ],
)
def test_numeric_model_explanation_is_rejected_before_finish_and_can_be_corrected(
    execution, explanation
):
    heat(execution)
    with pytest.raises(ValueError, match="逐字原文"):
        execution.complete("计算完成。", "completed", [], explanation)
    assert execution.trace.data["status"] == "running"
    assert "model_answer" not in execution.trace.data
    answer = execution.complete(
        "计算完成。", "completed", [], "比热越大，相同流量和温差下所需热负荷越大。"
    )
    assert "46.4444444444 kW" in answer and "补充说明" in answer


def test_numeric_source_quote_is_preserved_and_distinguished_from_current_result(execution):
    heat(execution, flow=2000)
    quote = "温差 1℃ = 1 K；这不是绝对温标的原点换算。"
    execution.trace.data["evidence"] = [
        {"chunk_id": "temperature", "text": "前文。" + quote + "后文。"}
    ]
    answer = execution.complete("热负荷完成。", "completed", ["temperature"], quote)
    assert "92.8888888889 kW" in answer
    assert "来源原文（temperature；非本轮计算结果）" in answer
    assert quote in answer


def test_uncited_or_invented_numeric_explanation_cannot_pass_as_a_source_quote(execution):
    heat(execution)
    quote = "温差 1℃ = 1 K。"
    execution.trace.data["evidence"] = [
        {"chunk_id": "cited", "text": "没有所需的定量关系。"},
        {"chunk_id": "uncited", "text": quote},
    ]
    with pytest.raises(ValueError, match="逐字原文"):
        execution.complete("计算完成。", "completed", ["cited"], quote)
    with pytest.raises(ValueError, match="逐字原文"):
        execution.complete("计算完成。", "completed", ["cited", "uncited"], "温差 2℃ = 2 K。")


def test_years_chapters_and_dates_are_kept_in_qualitative_explanation(execution):
    heat(execution)
    explanation = "2026-10-07 的第2章用稳态能量守恒解释显热公式。"
    assert explanation in execution.complete("已计算。", "completed", [], explanation)


@pytest.mark.parametrize("explanation", ["", None])
def test_final_tool_remains_compatible_with_optional_empty_explanation(execution, explanation):
    heat(execution)
    answer = FinalTool(execution).forward("已计算。", "completed", [], explanation)
    assert "46.4444444444 kW" in answer
    assert "model_explanation" not in execution.trace.data


@pytest.mark.parametrize("status", ["needs_input", "failed", "no_evidence", "out_of_scope"])
def test_partial_or_noncompleted_run_keeps_its_explanation_without_completed_numeric_answer(
    execution, status
):
    execution.set_plan([{"step_id": "s1", "goal": "换算流量", "tool_name": "convert_units"}])
    execution.execute(
        "convert_units", "s1", {"value": 1000, "from_unit": "kg/h", "to_unit": "kg/s"}
    )
    answer = "缺少比热，未完成热负荷计算。"
    assert execution.complete(answer, status, []) == answer
    assert "model_answer" not in execution.trace.data
