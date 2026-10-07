import json
from copy import deepcopy
from pathlib import Path

import pytest

from chem_agent.execution import Execution
from chem_agent.knowledge import KnowledgeBase
from chem_agent.trace import RunTrace

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def execution(tmp_path):
    kb = KnowledgeBase(ROOT / "data" / "knowledge")
    trace = RunTrace(tmp_path, "计算热负荷", {}, kb.version)
    return Execution(kb, trace)


def heat_plan():
    return [
        {"step_id": "s1", "goal": "换算流量", "tool_name": "convert_units", "depends_on": []},
        {
            "step_id": "s2",
            "goal": "计算热负荷",
            "tool_name": "calc_heat_duty",
            "depends_on": ["s1"],
        },
    ]


def heat_arguments():
    return {"mass_flow_kg_s": {"$ref": "s1.value"}, "specific_heat_kj_kg_k": 4.18, "delta_t_k": 40}


def test_real_result_is_resolved_and_persisted(execution):
    execution.set_plan(heat_plan())
    execution.execute(
        "convert_units", "s1", {"value": 2000, "from_unit": "kg/h", "to_unit": "kg/s"}
    )
    output = execution.execute("calc_heat_duty", "s2", heat_arguments())["output"]
    assert output["heat_duty_kw"] == pytest.approx(92.8888888889)
    call = execution.trace.data["calls"][-1]
    assert call["input_refs"][0]["argument"] == "mass_flow_kg_s"
    assert call["input_refs"][0]["ref"] == "s1.value"
    assert call["input_refs"][0]["value"] == pytest.approx(2000 / 3600)
    assert call["input_refs"][0]["unit"] == "kg/s"
    execution.complete("热负荷92.89 kW，恒比热且无相变。", "completed", [])
    persisted = json.loads(execution.trace.path.read_text())
    assert persisted["status"] == "completed"
    assert persisted["calls"][-1]["requested_arguments"]["mass_flow_kg_s"] == {"$ref": "s1.value"}


def test_copied_number_cannot_fake_dependency(execution):
    execution.set_plan(heat_plan())
    execution.execute(
        "convert_units", "s1", {"value": 1000, "from_unit": "kg/h", "to_unit": "kg/s"}
    )
    args = heat_arguments() | {"mass_flow_kg_s": 1000 / 3600}
    with pytest.raises(ValueError, match="引用"):
        execution.execute("calc_heat_duty", "s2", args)
    assert "s2" not in execution.results


def test_failed_conversion_blocks_downstream(execution):
    execution.set_plan(heat_plan())
    with pytest.raises(ValueError):
        execution.execute("convert_units", "s1", {"value": 1, "from_unit": "kg", "to_unit": "K"})
    with pytest.raises(ValueError, match="前序"):
        execution.execute("calc_heat_duty", "s2", heat_arguments())
    assert not execution.results
    assert all(c["status"] == "failed" for c in execution.trace.data["calls"])


@pytest.mark.parametrize(
    "reference", ["s1.missing", "s8.value", "__class__.__dict__", "s1.value.x"]
)
def test_invalid_references_are_rejected(execution, reference):
    execution.set_plan(heat_plan())
    execution.execute("convert_units", "s1", {"value": 1, "from_unit": "kg/h", "to_unit": "kg/s"})
    with pytest.raises(ValueError):
        execution.execute(
            "calc_heat_duty", "s2", heat_arguments() | {"mass_flow_kg_s": {"$ref": reference}}
        )


def test_wrong_tool_and_unregistered_steps_do_not_run(execution):
    with pytest.raises(ValueError, match="登记"):
        execution.execute("convert_units", "s1", {"value": 1, "from_unit": "kg", "to_unit": "g"})
    execution.set_plan(heat_plan())
    with pytest.raises(ValueError):
        execution.execute("calc_mass_balance", "s1", {"streams": []})


def test_cycle_and_duplicate_steps_are_rejected(execution):
    with pytest.raises(ValueError):
        execution.set_plan([heat_plan()[1], heat_plan()[0]])
    with pytest.raises(ValueError):
        execution.set_plan([heat_plan()[0], heat_plan()[0]])


def test_plan_cannot_be_replaced_after_execution(execution):
    execution.set_plan(heat_plan())
    with pytest.raises(ValueError):
        execution.set_plan(heat_plan())


def test_false_completion_and_fake_citation_are_rejected(execution):
    with pytest.raises(ValueError):
        execution.complete("done", "completed", [])
    with pytest.raises(ValueError, match="引用"):
        execution.complete("done", "no_evidence", ["fake-source"])
    execution.complete("请补充比热。", "needs_input", [])
    assert execution.trace.data["status"] == "needs_input"


def test_search_requires_real_citations(execution):
    execution.set_plan(
        [{"step_id": "s1", "goal": "检索", "tool_name": "search_knowledge", "depends_on": []}]
    )
    result = execution.execute("search_knowledge", "s1", {"query": "显热公式适用条件"})["output"]
    with pytest.raises(ValueError, match="引用"):
        execution.complete("显热公式Q=mcΔT", "completed", [])
    execution.complete(
        "恒比热条件下按流量、比热和温差计算。", "completed", [result["hits"][0]["chunk_id"]]
    )


def test_no_evidence_cannot_be_marked_completed(execution):
    execution.set_plan(
        [{"step_id": "s1", "goal": "检索", "tool_name": "search_knowledge", "depends_on": []}]
    )
    result = execution.execute("search_knowledge", "s1", {"query": "足球世界杯冠军"})["output"]
    assert result["status"] == "no_evidence"
    with pytest.raises(ValueError, match="证据"):
        execution.complete("unknown", "completed", [])
    execution.complete("资料不足。", "no_evidence", [])


@pytest.mark.parametrize("status", ["needs_input", "no_evidence", "failed", "out_of_scope"])
def test_final_answer_cannot_overwrite_a_finished_task(execution, status):
    execution.complete("首个最终答复。", status, [])
    original = deepcopy(execution.trace.data)
    persisted = execution.trace.path.read_text()
    with pytest.raises(ValueError, match="已经结束"):
        execution.complete("另一个答复。", "failed", [])
    assert execution.trace.data == original
    assert execution.trace.path.read_text() == persisted


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_completed_and_cancelled_tasks_also_reject_another_final_answer(execution, status):
    if status == "completed":
        execution.set_plan([heat_plan()[0]])
        execution.execute("convert_units", "s1", {"value": 1, "from_unit": "kg", "to_unit": "g"})
        execution.complete("1 kg = 1000 g。", "completed", [])
    else:
        execution.trace.finish("cancelled", "模拟外部取消。")
    original = deepcopy(execution.trace.data)
    with pytest.raises(ValueError, match="已经结束"):
        execution.complete("done", "failed", [])
    assert execution.trace.data == original


def test_other_search_evidence_cannot_hide_an_empty_required_search(execution):
    execution.set_plan(
        [
            {"step_id": step, "goal": "检索", "tool_name": "search_knowledge", "depends_on": []}
            for step in ("s1", "s2")
        ]
    )
    hit = execution.execute("search_knowledge", "s1", {"query": "显热公式"})["output"]
    empty = execution.execute("search_knowledge", "s2", {"query": "足球世界杯冠军"})["output"]
    assert hit["hits"] and empty["status"] == "no_evidence"
    with pytest.raises(ValueError, match="检索没有证据"):
        execution.complete("全部回答。", "completed", [hit["hits"][0]["chunk_id"]])
    assert execution.trace.data["status"] == "running"


def test_empty_search_blocks_calculation_until_the_same_search_is_retried(execution):
    execution.set_plan(
        [
            {"step_id": "s1", "goal": "检索", "tool_name": "search_knowledge", "depends_on": []},
            {
                "step_id": "s2",
                "goal": "热负荷",
                "tool_name": "calc_heat_duty",
                "depends_on": ["s1"],
            },
        ]
    )
    execution.execute("search_knowledge", "s1", {"query": "足球世界杯冠军"})
    args = {"mass_flow_kg_s": 1, "specific_heat_kj_kg_k": 4.18, "delta_t_k": 40}
    with pytest.raises(ValueError, match="前序检索没有证据"):
        execution.execute("calc_heat_duty", "s2", args)
    assert "s2" not in execution.results
    hit = execution.execute("search_knowledge", "s1", {"query": "显热公式适用条件"})["output"]
    assert hit["hits"]
    result = execution.execute("calc_heat_duty", "s2", args)
    assert result["output"]["heat_duty_kw"] == pytest.approx(167.2)
    execution.complete(
        "热负荷167.2 kW，恒比热且无相变。", "completed", [hit["hits"][0]["chunk_id"]]
    )
    assert execution.trace.data["status"] == "completed"
    with pytest.raises(ValueError, match="已经结束"):
        execution.execute("search_knowledge", "s1", {"query": "再次检索"})


def test_a_search_with_evidence_cannot_be_replaced(execution):
    execution.set_plan(
        [{"step_id": "s1", "goal": "检索", "tool_name": "search_knowledge", "depends_on": []}]
    )
    hit = execution.execute("search_knowledge", "s1", {"query": "显热公式"})["output"]
    with pytest.raises(ValueError, match="此步骤已完成"):
        execution.execute("search_knowledge", "s1", {"query": "足球世界杯冠军"})
    assert execution.results["s1"] == hit


def test_tool_latency_is_recorded_for_success_and_validation_failure(execution):
    execution.set_plan(heat_plan())
    with pytest.raises(ValueError):
        execution.execute("convert_units", "s1", {"value": 1, "from_unit": "kg", "to_unit": "K"})
    execution.execute("convert_units", "s1", {"value": 1, "from_unit": "kg/h", "to_unit": "kg/s"})
    assert [call["status"] for call in execution.trace.data["calls"]] == ["failed", "succeeded"]
    for call in execution.trace.data["calls"]:
        assert call["latency_ms"] >= 0
        assert call["finished_at"] >= call["started_at"]
