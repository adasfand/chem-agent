"""Regressions for trace persistence and dimensional result references."""

import json
import math

import pytest

from chem_agent.execution import Execution
from chem_agent.knowledge import KnowledgeBase
from chem_agent.trace import RunTrace


@pytest.fixture
def execution(tmp_path):
    knowledge = KnowledgeBase(tmp_path / "empty-knowledge")
    trace = RunTrace(tmp_path / "runs", "验证单位引用", {}, knowledge.version)
    return Execution(knowledge, trace)


def heat_plan():
    return [
        {"step_id": "s1", "goal": "换算", "tool_name": "convert_units", "depends_on": []},
        {"step_id": "s2", "goal": "热负荷", "tool_name": "calc_heat_duty", "depends_on": ["s1"]},
    ]


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_nonfinite_argument_is_rejected_without_corrupting_trace(execution, invalid):
    execution.set_plan(heat_plan())
    with pytest.raises(ValueError, match="有限数值"):
        execution.execute(
            "convert_units", "s1", {"value": invalid, "from_unit": "kg/h", "to_unit": "kg/s"}
        )
    execution.complete("输入包含非有限数值，无法继续。", "failed", [])
    persisted = json.loads(execution.trace.path.read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
    assert persisted["calls"][0]["status"] == "failed"
    assert "s1" not in execution.results
    assert isinstance(persisted["calls"][0]["requested_arguments"]["value"], str)


def test_flow_reference_converts_source_unit_to_target_parameter_unit(execution):
    execution.set_plan(heat_plan())
    execution.execute("convert_units", "s1", {"value": 1000, "from_unit": "kg/h", "to_unit": "g/s"})
    result = execution.execute(
        "calc_heat_duty",
        "s2",
        {
            "mass_flow_kg_s": {"$ref": "s1.value"},
            "specific_heat_kj_kg_k": 4.18,
            "delta_t_k": 40,
        },
    )
    assert result["output"]["heat_duty_kw"] == pytest.approx(46.4444444444)
    reference = execution.trace.data["calls"][-1]["input_refs"][0]
    assert reference["source_value"] == pytest.approx(1000 / 3.6)
    assert reference["source_unit"] == "g/s"
    assert reference["unit"] == "kg/s"
    assert reference["value"] == pytest.approx(1000 / 3600)


def test_temperature_difference_dependency_does_not_require_flow_reference(execution):
    execution.set_plan(heat_plan())
    execution.execute(
        "convert_units", "s1", {"value": 18, "from_unit": "delta_degF", "to_unit": "delta_degC"}
    )
    result = execution.execute(
        "calc_heat_duty",
        "s2",
        {
            "mass_flow_kg_s": 1,
            "specific_heat_kj_kg_k": 4.18,
            "delta_t_k": {"$ref": "s1.value"},
        },
    )
    assert result["output"]["heat_duty_kw"] == pytest.approx(41.8)
    reference = execution.trace.data["calls"][-1]["input_refs"][0]
    assert reference["argument"] == "delta_t_k"
    assert reference["source_unit"] == "delta_degC"
    assert reference["unit"] == "delta_K"


def test_absolute_temperature_cannot_supply_temperature_difference(execution):
    execution.set_plan(heat_plan())
    execution.execute("convert_units", "s1", {"value": 25, "from_unit": "degC", "to_unit": "K"})
    with pytest.raises(ValueError, match="不兼容"):
        execution.execute(
            "calc_heat_duty",
            "s2",
            {
                "mass_flow_kg_s": 1,
                "specific_heat_kj_kg_k": 4.18,
                "delta_t_k": {"$ref": "s1.value"},
            },
        )
    assert "s2" not in execution.results


def test_mass_balance_flow_reference_is_converted_to_kg_per_hour(execution):
    execution.set_plan(
        [
            {"step_id": "s1", "goal": "换算流量", "tool_name": "convert_units", "depends_on": []},
            {
                "step_id": "s2",
                "goal": "混合衡算",
                "tool_name": "calc_mass_balance",
                "depends_on": ["s1"],
            },
        ]
    )
    execution.execute("convert_units", "s1", {"value": 360, "from_unit": "kg/h", "to_unit": "kg/s"})
    result = execution.execute(
        "calc_mass_balance",
        "s2",
        {
            "streams": [
                {"flow_kg_h": {"$ref": "s1.value"}, "mass_fraction": 0.1},
                {"flow_kg_h": 360, "mass_fraction": 0},
            ],
        },
    )
    assert result["output"]["total_flow_kg_h"] == pytest.approx(720)
    assert result["output"]["mass_fraction"] == pytest.approx(0.05)
    reference = execution.trace.data["calls"][-1]["input_refs"][0]
    assert reference["argument"] == "streams[0].flow_kg_h"
    assert reference["source_unit"] == "kg/s"
    assert reference["unit"] == "kg/h"
