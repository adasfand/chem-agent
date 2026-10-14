"""A real nine-tool workflow, with only the model response supplied offline."""

from copy import deepcopy
from typing import get_args

import pytest
from test_agent import ScriptedModel

from chem_agent.agent import run_task
from chem_agent.inputs import supplied_density
from chem_agent.report import render_report
from chem_agent.tool_catalog import AGENT_TOOLS, TOOL_NAMES, ToolName

PLAN = [
    {
        "step_id": "s1",
        "goal": "检索混合显热及停留时间公式",
        "tool_name": "search_knowledge",
        "depends_on": [],
    },
    {"step_id": "s2", "goal": "混合衡算", "tool_name": "calc_mass_balance", "depends_on": ["s1"]},
    {"step_id": "s3", "goal": "换算质量流量", "tool_name": "convert_units", "depends_on": ["s2"]},
    {"step_id": "s4", "goal": "计算温差", "tool_name": "calc_temperature_change", "depends_on": []},
    {
        "step_id": "s5",
        "goal": "计算体积流量",
        "tool_name": "calc_volume_flow",
        "depends_on": ["s2"],
    },
    {"step_id": "s6", "goal": "两路分流", "tool_name": "calc_split_flow", "depends_on": ["s2"]},
    {
        "step_id": "s7",
        "goal": "名义停留时间",
        "tool_name": "calc_residence_time",
        "depends_on": ["s5"],
    },
    {
        "step_id": "s8",
        "goal": "显热负荷",
        "tool_name": "calc_heat_duty",
        "depends_on": ["s1", "s3", "s4"],
    },
    {
        "step_id": "s9",
        "goal": "恒功率运行传热量",
        "tool_name": "calc_heating_energy",
        "depends_on": ["s8"],
    },
]
ARGUMENTS = [
    {"query": "显热热负荷 单相 质量流量"},
    {
        "streams": [
            {"flow_kg_h": 100, "mass_fraction": 0.05},
            {"flow_kg_h": 400, "mass_fraction": 0},
        ]
    },
    {"value": {"$ref": "s2.total_flow_kg_h"}, "from_unit": "kg/h", "to_unit": "kg/s"},
    {"inlet_temperature_c": 25, "outlet_temperature_c": 65},
    {"mass_flow_kg_h": {"$ref": "s2.total_flow_kg_h"}, "density_kg_m3": 1000},
    {"total_flow_kg_h": {"$ref": "s2.total_flow_kg_h"}, "split_fraction": 0.3},
    {"vessel_volume_m3": 1, "volume_flow_m3_h": {"$ref": "s5.volume_flow_m3_h"}},
    {
        "mass_flow_kg_s": {"$ref": "s3.value"},
        "specific_heat_kj_kg_k": 4.18,
        "delta_t_k": {"$ref": "s4.delta_t_k"},
    },
    {"heat_duty_kw": {"$ref": "s8.heat_duty_kw"}, "duration_h": 2},
]


def test_nine_tool_plan_executes_batch_references_and_exports(settings):
    def factory(_, trace):
        def script(i):
            if i == 0:
                return [("set_plan", {"steps": deepcopy(PLAN)})] + [
                    (p["tool_name"], {"step_id": p["step_id"], "arguments": deepcopy(a)})
                    for p, a in zip(PLAN, ARGUMENTS)
                ]
            return (
                "final_answer",
                {
                    "answer": "已执行组合计算。",
                    "status": "completed",
                    "citations": [e["chunk_id"] for e in trace.data["evidence"]],
                },
            )

        return ScriptedModel(script)

    result = run_task(
        "比热明确给定4.18 kJ/(kg·K)，密度明确给定1000 kg/m3，完成混合后加热及分流停留时间计算。",
        settings,
        model_factory=factory,
    )
    assert result["status"] == "completed"
    assert len(result["plan"]) == 9 and len(result["calls"]) == 9
    assert result["tool_batches"][0]["status"] == "succeeded"
    assert all(s["algorithm"] for s in result["plan"])
    calls = {c["tool_name"]: c for c in result["calls"]}
    assert calls["calc_volume_flow"]["output"]["volume_flow_m3_h"] == 0.5
    assert calls["calc_residence_time"]["output"]["residence_time_h"] == 2
    assert calls["calc_split_flow"]["output"]["branch_flow_kg_h"] == 150
    assert calls["calc_heating_energy"]["output"]["energy_kwh"] == pytest.approx(46.4444444444)
    assert calls["calc_volume_flow"]["input_provenance"][0]["source"] == "user"
    assert calls["calc_heat_duty"]["input_refs"][1]["unit"] == "delta_K"
    assert "传热量" in result["answer"] and "名义停留时间" in result["answer"]
    exported = render_report(result)
    assert "体积流量" in exported and "167200" in exported
    assert set(get_args(ToolName)) == TOOL_NAMES == {t["name"] for t in AGENT_TOOLS}


@pytest.fixture
def settings(tmp_path):
    from chem_agent.config import Settings

    cards = tmp_path / "data/knowledge"
    cards.mkdir(parents=True)
    (cards / "heat.md").write_text(
        "# 显热热负荷\n来源：教学测试\n\n## 条件\n单相恒比热显热负荷由质量流量、比热和温差计算。",
        encoding="utf-8",
    )
    return Settings(root=tmp_path)


@pytest.mark.parametrize("text,value", [("密度为1000 kg/m3", 1000), ("密度为1 g/cm³", 1000)])
def test_density_matches_explicit_user_units(text, value):
    assert supplied_density(value, [text])["value"] == 1000


@pytest.mark.parametrize(
    "latest",
    ["密度未知", "撤回密度", "密度改为900", "密度为900 kg/m3", "密度为900 kg/m3或1000 kg/m3"],
)
def test_density_update_cannot_revive_an_old_value(latest):
    with pytest.raises(ValueError):
        supplied_density(1000, ["密度为1000 kg/m3", latest])


@pytest.mark.parametrize("unit", ["kg/m3/s", "kg/m3 / s", "kg/m3·K"])
def test_density_rejects_extended_dimensions(unit):
    with pytest.raises(ValueError):
        supplied_density(1000, ["密度为1000 " + unit])


@pytest.mark.parametrize(
    "sentence",
    ["停留时间为999小时。", "体积流量为999 m³/h。", "传热量为999 kWh。", "分流比例为0.9。"],
)
def test_extended_numeric_explanations_require_real_sources(sentence):
    from chem_agent.answers import calculation_explanation

    with pytest.raises(ValueError):
        calculation_explanation(sentence, [], [], [])


def test_temperature_reference_rejects_power_units(settings):
    from chem_agent.execution import Execution
    from chem_agent.knowledge import KnowledgeBase
    from chem_agent.trace import RunTrace

    kb = KnowledgeBase(settings.knowledge_dir)
    execution = Execution(kb, RunTrace(settings.runs_dir, "计算温差", {}, kb.version))
    execution.set_plan(
        [
            {"step_id": "s1", "goal": "换算功率", "tool_name": "convert_units"},
            {
                "step_id": "s2",
                "goal": "温差",
                "tool_name": "calc_temperature_change",
                "depends_on": ["s1"],
            },
        ]
    )
    execution.execute("convert_units", "s1", {"value": 50, "from_unit": "kW", "to_unit": "kW"})
    with pytest.raises(ValueError, match="不兼容"):
        execution.execute(
            "calc_temperature_change",
            "s2",
            {"inlet_temperature_c": {"$ref": "s1.value"}, "outlet_temperature_c": 65},
        )
