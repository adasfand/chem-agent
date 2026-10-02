"""Reports use observable outputs and safely export untrusted text."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from chem_agent.calculations import calc_heat_duty, calc_mass_balance, convert_units
from chem_agent.report import render_report


def completed_result():
    return {
        "run_id": "20261002T100000-test",
        "status": "completed",
        "question": "1000 kg/h液体升温40 K，比热4.18 kJ/(kg·K)，求热负荷。",
        "answer": "模型答复：热负荷999 kW。",
        "started_at": "2026-10-02T10:00:00+00:00",
        "finished_at": "2026-10-02T10:00:03+00:00",
        "knowledge_version": "test-version",
        "plan": [
            {
                "step_id": "s1",
                "goal": "换算流量",
                "tool_name": "convert_units",
                "status": "succeeded",
            },
            {
                "step_id": "s2",
                "goal": "计算热负荷",
                "tool_name": "calc_heat_duty",
                "status": "succeeded",
            },
        ],
        "calls": [
            {
                "step_id": "s1",
                "tool_name": "convert_units",
                "status": "succeeded",
                "output": convert_units(1000, "kg/h", "kg/s"),
            },
            {
                "step_id": "s2",
                "tool_name": "calc_heat_duty",
                "status": "succeeded",
                "output": calc_heat_duty(1000 / 3600, 4.18, 40),
            },
        ],
        "citations": ["heat:formula"],
        "evidence": [
            {
                "chunk_id": "heat:formula",
                "title": "显热公式",
                "source": "自编教学说明",
                "text": "稳态显热负荷等于流量、比热、温差之积。",
            },
            {
                "chunk_id": "heat:scope",
                "title": "显热限制",
                "source": "自编教学说明",
                "text": "不适用于相变。",
            },
        ],
    }


def test_completed_report_separates_model_answer_from_actual_numeric_results():
    result = completed_result()
    original = deepcopy(result)
    report = render_report(result)
    assert "# 化工任务运行报告" in report
    assert "状态：已完成" in report
    assert result["question"] in report
    assert result["answer"] in report
    numbers = report.split("## 实际工具结果", 1)[1].split("## 执行计划", 1)[0]
    assert "46.4444444444" in numbers
    assert "999" not in numbers
    assert "0.277777777778" in numbers
    assert "kg/s" in numbers and "kW" in numbers
    assert "2 次成功工具调用" in numbers
    assert "无相变" in report
    assert "20261002T100000-test" in report
    assert result == original


def test_missing_input_report_preserves_question_without_inventing_result():
    report = render_report(
        {
            "run_id": "missing-input",
            "status": "needs_input",
            "question": "给定流量1000 kg/h，请计算热负荷。",
            "answer": "请补充比热和温差。",
            "calls": [],
            "plan": [],
            "evidence": [],
            "citations": [],
        }
    )
    assert "等待补充参数" in report
    assert "请补充比热和温差。" in report
    assert "没有可展示的成功数值计算结果" in report
    assert "未登记执行计划" in report
    assert "没有检索依据" in report
    assert "46.44" not in report


def test_failed_tool_output_is_never_reported_as_success():
    result = completed_result()
    result["status"] = "failed"
    result["answer"] = "单位错误，计算未完成。"
    result["calls"][1].update(status="failed", error="质量流量单位不兼容。")
    result["calls"][1]["output"]["heat_duty_kw"] = 123456789
    result["plan"][1]["status"] = "failed"
    report = render_report(result)
    assert "执行未完成" in report
    assert "1 次成功工具调用" in report
    assert "质量流量单位不兼容。" in report
    assert "123456789" not in report
    assert "### 本次计算的工具假设" not in report


def test_sources_distinguish_citations_retrieval_and_missing_ids():
    result = completed_result()
    result["citations"].append("fabricated:missing")
    result["evidence"].append(deepcopy(result["evidence"][0]))
    report = render_report(result)
    assert "### 依据 1 · 实际引用" in report
    assert "### 依据 2 · 仅检索，未引用" in report
    assert "### 依据 3" not in report
    assert "heat:formula" in report and "heat:scope" in report
    assert "1 个引用编号未出现在检索记录中" in report
    assert "fabricated:missing" not in report


def test_report_excludes_private_configuration_requests_and_paths():
    result = completed_result()
    result.update(
        config={
            "api_key": "private-not-sk-key",
            "authorization": "Bearer private-token",
            "nested": {"password": "hidden-password"},
            "base_url": "https://private-provider.example",
        },
        trace_path="/Users/person/Private Runs/trace.json",
        model_requests=[{"messages": [{"content": "raw-model-request-secret"}]}],
    )
    result["answer"] = (
        "private-not-sk-key /Users/person/Private Runs/trace.json file:///etc/secret.txt"
    )
    result["evidence"][0]["source"] = r"C:\Users\person\secret.txt"
    result["calls"][1]["output"]["assumptions"].append("记录位置 /home/person/private/file.txt")
    result["calls"][1]["output"]["assumptions"].append("日志路径为/Users/private-person/log.txt")
    report = render_report(result)
    for private in (
        "private-not-sk-key",
        "Bearer private-token",
        "hidden-password",
        "private-provider.example",
        "raw-model-request-secret",
        "trace_path",
        "/Users/person",
        "secret.txt",
        "/home/person",
        "private-person",
    ):
        assert private not in report
    assert "[redacted]" in report
    assert "[本地路径已隐藏]" in report
    assert "kg/s" in report


def test_unknown_fields_and_nonfinite_outputs_are_not_exported():
    result = completed_result()
    result["calls"][1]["output"].update(heat_duty_kw=float("nan"), private_metadata="do-not-export")
    result["calls"][0]["output"]["value"] = True
    report = render_report(result)
    assert "do-not-export" not in report
    assert "nan" not in report
    assert "True" not in report


def test_external_markdown_html_and_fences_stay_literal():
    hostile = "```\n<script>alert(1)</script>\n![remote](https://example.com/track)\n```"
    result = completed_result()
    result["answer"] = hostile
    result["plan"][0]["goal"] = "bad | `cell`\n![remote](https://example.com)"
    report = render_report(result)
    assert f"````text\n{hostile}\n````" in report
    assert r"bad \| `cell`" in report
    assert "sk-" not in render_report({"answer": "sk-abcdefghijklmnop", "status": "failed"})


def test_mass_balance_outputs_keep_fraction_and_flow_units():
    result = completed_result()
    result["calls"] = [
        {
            "step_id": "s1",
            "tool_name": "calc_mass_balance",
            "status": "succeeded",
            "output": calc_mass_balance(
                [{"flow_kg_h": 100, "mass_fraction": 0.05}, {"flow_kg_h": 400, "mass_fraction": 0}]
            ),
        }
    ]
    report = render_report(result)
    assert "500" in report
    assert "kg/h" in report
    assert "0.01" in report
    assert "1（质量分数，0–1）" in report
    assert "稳态、完全混合" in report


def test_existing_verified_trace_can_be_exported_without_replaying():
    path = Path(__file__).resolve().parents[1] / "docs/validation/20260929T153752-280c5288c2.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    report = render_report(result)
    assert result["run_id"] in report
    assert "等待补充参数" in report
    assert "比热容" in report


def test_requires_run_record_object():
    with pytest.raises(ValueError, match="运行记录对象"):
        render_report(None)


def test_follow_up_report_includes_parent_and_user_context_without_assistant_replay():
    result = completed_result()
    result.update(
        question="比热为4.18 kJ/(kg·K)。",
        parent_run_id="20261002T095959-parent",
        history=[
            {"role": "user", "content": "流量1000 kg/h，从25℃升至65℃，请计算热负荷。"},
            {"role": "assistant", "content": "先前助手的长答复，不应重复到报告。"},
        ],
    )
    original = deepcopy(result)
    report = render_report(result)
    context = report.split("## 关联上下文", 1)[1].split("## 答复", 1)[0]
    assert "20261002T095959-parent" in context
    assert "流量1000 kg/h，从25℃升至65℃" in context
    assert "先前助手的长答复" not in report
    assert "比热为4.18 kJ/(kg·K)。" in report
    assert result == original


def test_context_keeps_only_latest_four_user_inputs_and_handles_missing_history():
    result = completed_result()
    result["history"] = [{"role": "user", "content": f"用户输入-{index}"} for index in range(6)] + [
        {"role": "user", "content": None},
        {"role": "system", "content": "private-system"},
    ]
    report = render_report(result)
    assert "用户输入-0" not in report and "用户输入-1" not in report
    assert report.index("用户输入-2") < report.index("用户输入-5")
    assert "private-system" not in report
    assert "## 关联上下文" not in render_report(completed_result())
    result.update(parent_run_id="parent-only", history=None)
    report = render_report(result)
    assert "parent-only" in report
    assert "未记录可展示的先前用户输入" in report


def test_context_and_record_warning_preserve_fencing_and_redaction():
    hostile = "```\n<script>alert(1)</script>\n![remote](https://example.com/track)\n```"
    result = completed_result()
    result.update(
        parent_run_id="parent `id` hidden-test-key",
        history=[
            {"role": "user", "content": hostile},
            {"role": "user", "content": "密钥 hidden-test-key；来源 /Users/private/source.txt"},
        ],
        config={"api_key": "hidden-test-key"},
        record_warning="写入 /Users/private/trace.json 失败：hidden-test-key",
    )
    report = render_report(result)
    assert f"````text\n{hostile}\n````" in report
    assert "## 记录保存提示" in report
    assert "本报告根据当前内存中的运行记录生成" in report
    assert "hidden-test-key" not in report
    assert "/Users/private" not in report
    assert "[redacted]" in report
    assert "[本地路径已隐藏]" in report
    assert "## 记录保存提示" not in render_report(completed_result())
