"""Offline server-side dependency and citation guards; no model requests."""
from types import SimpleNamespace

import pytest

from chem_agent.execution import ExecutionContext
from chem_agent.trace import RunTrace


def context(tmp_path):
    return ExecutionContext(RunTrace(tmp_path), None, SimpleNamespace(max_steps=12, top_k=4, min_score=0.05))


def plan(heat_parameter="mass_flow_kg_s"):
    return [
        {"step_id": "s1", "goal": "换算", "tool_name": "convert_units", "depends_on": [],
         "input_refs": {"value": "user:题设", "from_unit": "user:原单位", "to_unit": "user:目标单位"}},
        {"step_id": "s2", "goal": "计算", "tool_name": "calc_heat_duty", "depends_on": ["s1"],
         "input_refs": {"mass_flow_kg_s": "user:题设流量", "cp_kj_kg_k": "user:题设比热",
                        "delta_t_k": "user:温差", heat_parameter: "s1.value"}},
    ]


def test_resolves_actual_value_and_blocks_early_call(tmp_path):
    ctx = context(tmp_path)
    ctx.record_plan(plan())
    with pytest.raises(ValueError):
        ctx.execute("calc_heat_duty", "s2", {"cp_kj_kg_k": 4.18, "delta_t_k": 40})
    assert ctx.status["s2"] == "failed"
    ctx.execute("convert_units", "s1", {"value": 1000, "from_unit": "kg/h", "to_unit": "kg/s"})
    result = ctx.execute("calc_heat_duty", "s2", {"mass_flow_kg_s": 999, "cp_kj_kg_k": 4.18, "delta_t_k": 40})
    assert result["output"]["inputs"]["mass_flow_kg_s"] == pytest.approx(1000 / 3600)
    assert result["output"]["heat_duty_kw"] == pytest.approx(46.4444444444)


def test_wrong_cp_unit_reference_is_rejected(tmp_path):
    ctx = context(tmp_path)
    ctx.record_plan(plan(heat_parameter="cp_kj_kg_k"))
    ctx.execute("convert_units", "s1", {"value": 4.18, "from_unit": "kJ/(kg*K)", "to_unit": "J/(kg*K)"})
    with pytest.raises(ValueError):
        ctx.execute("calc_heat_duty", "s2", {"mass_flow_kg_s": 1, "delta_t_k": 40})
    assert "s2" not in ctx.outputs


def test_completed_plan_immutable_and_invented_citation_rejected(tmp_path):
    ctx = context(tmp_path)
    ctx.record_plan(plan()[:1])
    ctx.execute("convert_units", "s1", {"value": 1, "from_unit": "kg/h", "to_unit": "kg/s"})
    modified = plan()[:1]
    modified[0]["goal"] = "篡改已经执行的步骤"
    with pytest.raises(ValueError):
        ctx.record_plan(modified)
    with pytest.raises(ValueError):
        ctx.validate_answer("答案 [来源:invented:1]")
