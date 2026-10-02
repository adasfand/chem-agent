"""Small acceptance suite using real DeepSeek requests; never run during offline tests."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from chem_agent.agent import run_task
from chem_agent.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def knowledge_check(result):
    assert result["status"] == "completed"
    assert outputs(result, "search_knowledge") and result["citations"]
    # smolagents encodes tool observations as user messages in this adapter.
    messages = [
        m
        for request in result["model_requests"]
        for m in request["messages"]
        if m["role"] != "system"
    ]
    context = str(messages)
    assert any(
        hit["chunk_id"] in context and hit["text"].splitlines()[0] in context
        for hit in result["evidence"]
    )


def outputs(result, tool):
    return [
        c["output"]
        for c in result["calls"]
        if c["tool_name"] == tool and c["status"] == "succeeded"
    ]


def check_heat(result, expected):
    values = outputs(result, "calc_heat_duty")
    assert result["status"] == "completed", result["status"]
    assert values and math.isclose(values[-1]["heat_duty_kw"], expected, rel_tol=1e-9)
    assert result["citations"]
    assert any(c["input_refs"] for c in result["calls"] if c["tool_name"] == "calc_heat_duty")


def main():
    settings = Settings.load(ROOT)
    examples = {
        e["id"]: e["question"] for e in json.loads((ROOT / "examples/tasks.json").read_text())
    }
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live",
        "model": settings.model,
        "cases": [],
    }
    report_path = ROOT / "runs" / "live_validation.json"

    def run(case_id, question, check, history=None):
        result = run_task(question, settings, history=history)
        entry = {"case": case_id, "run_id": result["run_id"], "status": result["status"]}
        try:
            check(result)
            entry["passed"] = True
        except (AssertionError, KeyError, IndexError) as exc:
            entry.update(passed=False, error=str(exc) or "验收条件未满足")
        report["cases"].append(entry)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        return result

    def balance_check(r):
        assert r["status"] == "completed"
        out = outputs(r, "calc_mass_balance")[-1]
        assert out["total_flow_kg_h"] == 500
        assert math.isclose(out["mass_fraction"], 0.01)
        assert r["citations"]

    def unit_check(r):
        assert r["status"] == "completed"
        assert math.isclose(outputs(r, "convert_units")[-1]["value"], 2500)

    def missing_check(r):
        assert r["status"] == "needs_input"
        assert not outputs(r, "calc_heat_duty")

    def invalid_check(r):
        assert r["status"] in {"needs_input", "failed", "out_of_scope"}
        assert not outputs(r, "convert_units")

    run("knowledge", examples["knowledge"], knowledge_check)
    run("heat", examples["heat"], lambda r: check_heat(r, 1000 / 3600 * 4.18 * 40))
    run(
        "heat_changed_input",
        examples["heat"].replace("1000", "2000"),
        lambda r: check_heat(r, 2000 / 3600 * 4.18 * 40),
    )
    run("balance", examples["balance"], balance_check)
    run("units", examples["units"], unit_check)
    missing = run("missing_parameter", examples["missing"], missing_check)
    run(
        "follow_up",
        "比热为4.18 kJ/(kg·K)，假设单相、恒比热、无相变且忽略热损失。",
        lambda r: check_heat(r, 1000 / 3600 * 4.18 * 40),
        history=[
            {"role": "user", "content": examples["missing"]},
            {"role": "assistant", "content": missing["answer"]},
        ],
    )
    run("incompatible_units", "请把5 kg换算为K。", invalid_check)
    report["passed"] = all(case["passed"] for case in report["cases"])
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
