"""Verify retrieval dependencies and observable context evidence."""

import json

import pytest

from chem_agent.execution import Execution
from chem_agent.knowledge import KnowledgeBase
from chem_agent.observability import context_evidence
from chem_agent.trace import RunTrace


@pytest.fixture
def project(tmp_path):
    knowledge = tmp_path / "data/knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "heat.md").write_text(
        "# 显热\n来源：教学资料\n## 公式\n热负荷等于流量乘以比热与温差。", encoding="utf-8"
    )
    examples = tmp_path / "examples"
    examples.mkdir()
    (examples / "tasks.json").write_text(
        json.dumps(
            [
                {"id": name, "question": "问题"}
                for name in ("knowledge", "heat", "balance", "units", "missing")
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_context_evidence_requires_both_id_and_original_text():
    base = {
        "evidence": [{"chunk_id": "heat:x", "title": "显热", "text": "原文公式"}],
        "model_requests": [{"messages": [{"role": "user", "content": "只有编号heat:x"}]}],
    }
    assert context_evidence(base) == []
    base["model_requests"].append(
        {
            "status": "succeeded",
            "messages": [
                {"role": "user", "content": "heat:x 原文公式"},
                {"role": "assistant", "content": "私有思考"},
            ],
        }
    )
    assert context_evidence(base) == [
        {"chunk_id": "heat:x", "title": "显热", "request_indices": [2]}
    ]
    assert "私有" not in str(context_evidence(base))


def test_failed_model_request_is_not_successful_context_evidence():
    result = {
        "evidence": [{"chunk_id": "heat:x", "title": "显热", "text": "原文公式"}],
        "model_requests": [
            {"status": "failed", "messages": [{"role": "user", "content": "heat:x 原文公式"}]}
        ],
    }
    assert context_evidence(result) == []


def test_model_calculation_requires_successful_retrieval_dependency(project):
    trace = RunTrace(project / "runs", "计算显热", {}, "test", mode="offline_test")
    execution = Execution(KnowledgeBase(project / "data/knowledge"), trace, require_retrieval=True)
    with pytest.raises(ValueError, match="先检索"):
        execution.set_plan([{"step_id": "s1", "goal": "计算", "tool_name": "calc_heat_duty"}])
    execution.set_plan(
        [
            {"step_id": "s1", "goal": "检索", "tool_name": "search_knowledge"},
            {"step_id": "s2", "goal": "计算", "tool_name": "calc_heat_duty", "depends_on": ["s1"]},
        ]
    )
    execution.execute("search_knowledge", "s1", {"query": "不会命中的ABCDEFGH", "top_k": 1})
    with pytest.raises(ValueError):
        execution.execute(
            "calc_heat_duty",
            "s2",
            {"mass_flow_kg_s": 1, "specific_heat_kj_kg_k": 4.18, "delta_t_k": 40},
        )
    assert not any(
        call["status"] == "succeeded" and call["tool_name"] == "calc_heat_duty"
        for call in trace.data["calls"]
    )
