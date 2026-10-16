"""Check the complete delivery example, including actual result references."""

import shutil
from pathlib import Path

import pytest

from chem_agent.config import Settings
from scripts.demo_continuous import run_continuous_demo

ROOT = Path(__file__).resolve().parents[1]


def test_continuous_delivery_balances_heat_and_residence_time(tmp_path):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    result = run_continuous_demo(Settings(root=tmp_path))
    assert result["status"] == "completed"
    assert result["mode"] == "offline_demo"
    assert not result["model_requests"]
    calls = {call["step_id"]: call for call in result["calls"]}
    assert len(calls) == 11
    assert all(call["status"] == "succeeded" for call in calls.values())
    mix = calls["s2"]["output"]
    assert mix["total_flow_kg_h"] == 3000
    assert mix["component_flow_kg_h"] == 180
    assert mix["mass_fraction"] == pytest.approx(0.06)
    assert calls["s7"]["output"]["heat_duty_kw"] == pytest.approx(95)
    assert calls["s8"]["output"]["heat_duty_kw"] == pytest.approx(190 / 3)
    assert calls["s9"]["output"]["heat_duty_kw"] == pytest.approx(
        calls["s7"]["output"]["heat_duty_kw"] + calls["s8"]["output"]["heat_duty_kw"]
    )
    assert calls["s10"]["output"]["volume_flow_m3_h"] == pytest.approx(20 / 7)
    assert calls["s11"]["output"]["residence_time_min"] == pytest.approx(31.5)
    refs = [ref for call in calls.values() for ref in call.get("input_refs", [])]
    assert len(refs) == 9
    for ref in refs:
        step, field = ref["ref"].split(".")
        assert ref["value"] == calls[step]["output"][field]
    assert result["citations"] and result["evidence"]
