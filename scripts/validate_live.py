"""Real-model acceptance cases; imports and default pytest never make API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chem_agent.agent import run_task
from chem_agent.config import Settings
from chem_agent.knowledge import KnowledgeBase
from chem_agent.retrieval import HybridRetriever

ROOT = Path(__file__).resolve().parents[1]
_BATCH_ERROR = "每次回复只允许调用一个工具"
_FINAL_ERROR = "Error executing tool 'final_answer'"
_HEAT_CONDITIONS = {
    "稳态": r"稳态",
    "单相": r"单相",
    "恒比热": r"恒比热|比热(?:容)?[^，。；\n]*(?:常数|不变)",
    "无反应": r"无(?:化学)?反应(?!热)",
    "无相变": r"无相变",
    "忽略热损失": r"(?:忽略|无)(?:热损失|热损|散热)",
}
_BALANCE_CONDITIONS = {
    "稳态": r"稳态",
    "无反应": r"无(?:化学)?反应(?!热)",
    "无积累": r"无积累|积累(?:为|等于)?零",
    "无泄漏": r"无泄漏",
    "充分混合": r"充分混合|完全混合",
}


@dataclass(frozen=True)
class EvaluationSettings(Settings):
    """Reuse existing index/cache while evaluating this project's code and data."""

    project_root: Path = ROOT

    @property
    def knowledge_dir(self) -> Path:
        return self.project_root / "data" / "knowledge"

    @property
    def runs_dir(self) -> Path:
        return self.project_root / "runs"


def prepare_settings(
    settings: Settings, index_root: Path | None = None, backend: str = "auto"
) -> tuple[EvaluationSettings, dict]:
    if backend not in {"auto", "lexical", "lightrag"}:
        raise ValueError("未知检索后端。")
    selected_root = index_root.expanduser().resolve() if index_root else settings.root
    evaluation = EvaluationSettings(
        root=selected_root,
        api_key=settings.api_key,
        base_url=settings.base_url,
        model=settings.model,
        request_timeout=settings.request_timeout,
        max_steps=settings.max_steps,
        project_root=settings.root,
    )
    current = KnowledgeBase(evaluation.knowledge_dir)
    if (
        index_root
        and current.version != KnowledgeBase(selected_root / "data" / "knowledge").version
    ):
        raise ValueError("源索引项目与当前项目知识版本不同，不能复用该索引。")
    state = HybridRetriever(evaluation).index_status
    if (index_root or backend == "lightrag") and state["state"] != "ready":
        raise ValueError("指定的 LightRAG 索引未就绪；未开始任何模型请求。")
    if backend == "lexical" and state["state"] == "ready":
        raise ValueError("当前索引已就绪，不能将真实图谱查询标记为词法评估。")
    return evaluation, state


def successful_calls(result: dict, tool: str) -> list[dict]:
    return [
        call
        for call in result["calls"]
        if call["tool_name"] == tool and call["status"] == "succeeded"
    ]


def outputs(result: dict, tool: str) -> list[dict]:
    return [call["output"] for call in successful_calls(result, tool)]


def close_number(actual: Any, expected: float, label: str) -> None:
    assert not isinstance(actual, bool) and isinstance(actual, (int, float)), label
    assert math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12), (
        label
    )


def check_displayed_number(answer: str, expected: float, unit: str) -> None:
    text = answer.replace("*", "")
    pattern = rf"(?<![\d.])([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*{re.escape(unit)}(?![A-Za-z])"
    matches = list(re.finditer(pattern, text))
    # Permit presentation rounding (46.44 kW) without accepting a wrong value.
    assert any(
        math.isclose(float(match[1]), expected, rel_tol=1e-9, abs_tol=0.005) for match in matches
    ), f"用户可见回答缺少正确数值及单位：{expected:.12g} {unit}"


def check_conditions(answer: str, conditions: dict[str, str]) -> None:
    for label, pattern in conditions.items():
        assert re.search(pattern, answer), f"用户可见回答缺少前提：{label}"


def message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    return ""


def knowledge_check(result: dict) -> None:
    assert result["status"] == "completed", result["status"]
    assert successful_calls(result, "search_knowledge"), "没有成功检索"
    evidence = {hit["chunk_id"]: hit for hit in result["evidence"]}
    assert result["citations"] and set(result["citations"]) <= evidence.keys(), "引用没有实际来源"
    # smolagents encodes tool observations as user messages in this adapter.
    context = "\n".join(
        message_text(message)
        for request in result["model_requests"]
        for message in request["messages"]
        if message["role"] != "system"
    )
    for citation in result["citations"]:
        hit = evidence[citation]
        # Tool observations may serialize text as a Python repr or JSON string.
        encodings = (hit["text"], repr(hit["text"]), json.dumps(hit["text"], ensure_ascii=False))
        assert citation in context and any(text in context for text in encodings), (
            "引用原文未进入模型上下文"
        )


def check_reference(
    result: dict,
    call: dict,
    argument: str,
    *,
    source_tool: str,
    source_field: str,
    expected: float,
    unit: str,
) -> dict:
    requested = call["requested_arguments"].get(argument)
    assert isinstance(requested, dict) and set(requested) == {"$ref"}, f"{argument} 没有真实 $ref"
    reference = requested["$ref"]
    assert isinstance(reference, str) and reference.endswith(f".{source_field}"), "引用字段不正确"
    source_id, field = reference.split(".", 1)
    assert field == source_field, "引用字段不正确"
    steps = {step["step_id"]: step for step in result["plan"]}
    assert source_id in steps[call["step_id"]]["depends_on"], "引用未声明为依赖"
    preceding = result["calls"][: result["calls"].index(call)]
    sources = [
        prior
        for prior in preceding
        if prior["step_id"] == source_id
        and prior["tool_name"] == source_tool
        and prior["status"] == "succeeded"
    ]
    assert sources, "引用来源未先成功执行"
    source = sources[-1]
    refs = [record for record in call["input_refs"] if record["argument"] == argument]
    assert len(refs) == 1 and refs[0]["ref"] == reference, "input_refs 与请求的引用不一致"
    record = refs[0]
    assert record["unit"] == unit, "引用目标单位不正确"
    source_unit = source["output"].get("unit") if source_field == "value" else "kg/h"
    assert record["source_unit"] == source_unit, "引用来源单位不正确"
    close_number(record["source_value"], source["output"][source_field], "引用未读取实际输出")
    close_number(record["value"], expected, "引用解析后的数值不正确")
    close_number(call["arguments"][argument], expected, "工具实际输入与引用不一致")
    return source


def check_heat(result: dict, expected: float) -> None:
    knowledge_check(result)
    calls = successful_calls(result, "calc_heat_duty")
    assert calls, "没有成功执行显热计算"
    call = calls[-1]
    close_number(call["output"]["heat_duty_kw"], expected, "显热工具结果不正确")
    close_number(call["arguments"]["specific_heat_kj_kg_k"], 4.18, "比热未采用用户输入")
    close_number(call["arguments"]["delta_t_k"], 40, "温差未采用用户输入")
    conversion = check_reference(
        result,
        call,
        "mass_flow_kg_s",
        source_tool="convert_units",
        source_field="value",
        expected=expected / (4.18 * 40),
        unit="kg/s",
    )
    close_number(
        conversion["arguments"]["value"], expected / (4.18 * 40) * 3600, "流量未采用用户输入"
    )
    assert conversion["arguments"]["from_unit"] == "kg/h", "流量来源单位不正确"
    check_displayed_number(result["answer"], expected, "kW")
    check_conditions(result["answer"], _HEAT_CONDITIONS)


def balance_check(result: dict) -> None:
    knowledge_check(result)
    calls = successful_calls(result, "calc_mass_balance")
    assert calls, "没有成功执行混合衡算"
    call = calls[-1]
    streams = call["arguments"]["streams"]
    assert sorted(streams, key=lambda stream: stream["flow_kg_h"]) == [
        {"flow_kg_h": 100, "mass_fraction": 0.05},
        {"flow_kg_h": 400, "mass_fraction": 0},
    ], "混合工具输入与用户流股不一致"
    out = call["output"]
    for field, expected in (
        ("total_flow_kg_h", 500),
        ("component_flow_kg_h", 5),
        ("mass_fraction", 0.01),
    ):
        close_number(out[field], expected, f"混合工具 {field} 不正确")
    check_displayed_number(result["answer"], 500, "kg/h")
    check_displayed_number(result["answer"], 1, "%")
    check_conditions(result["answer"], _BALANCE_CONDITIONS)


def mixed_heat_check(result: dict) -> None:
    balance_check(result)
    check_heat(result, 500 / 3600 * 4.18 * 40)
    heat = successful_calls(result, "calc_heat_duty")[-1]
    conversion = check_reference(
        result,
        heat,
        "mass_flow_kg_s",
        source_tool="convert_units",
        source_field="value",
        expected=500 / 3600,
        unit="kg/s",
    )
    assert conversion["arguments"]["from_unit"] == "kg/h", "混合流量换算来源单位不正确"
    assert conversion["arguments"]["to_unit"] == "kg/s", "混合流量未换算到 kg/s"
    check_reference(
        result,
        conversion,
        "value",
        source_tool="calc_mass_balance",
        source_field="total_flow_kg_h",
        expected=500,
        unit="kg/h",
    )


def unit_check(result: dict) -> None:
    assert result["status"] == "completed", result["status"]
    call = successful_calls(result, "convert_units")[-1]
    assert call["arguments"] == {"value": 2.5, "from_unit": "MPa", "to_unit": "kPa"}
    assert call["output"]["unit"] == "kPa"
    close_number(call["output"]["value"], 2500, "换算结果不正确")
    check_displayed_number(result["answer"], 2500, "kPa")


def temperature_explanation_check(result: dict) -> None:
    knowledge_check(result)
    calls = [
        call
        for call in successful_calls(result, "convert_units")
        if call["arguments"]["from_unit"] in {"degC", "℃", "°C", "摄氏度", "C"}
        and call["arguments"]["to_unit"] == "K"
    ]
    assert calls, "没有执行摄氏温度到 K 的换算"
    call = calls[-1]
    close_number(call["arguments"]["value"], 25, "温度未采用用户输入")
    close_number(call["output"]["value"], 298.15, "绝对温度换算结果不正确")
    assert call["output"]["unit"] == "K", "绝对温度结果单位不正确"
    answer = result["answer"]
    check_displayed_number(answer, 298.15, "K")
    markers = [marker for marker in ("补充说明", "来源原文") if marker in answer]
    assert markers, "复合问题的概念解释被数值答复覆盖"
    explanation = answer.split(markers[0], 1)[1]
    assert "绝对温度" in explanation and "温差" in explanation, "未解释两个量的区别"
    assert re.search(r"原点|零点|偏移|273\.15", explanation), "未解释温标原点或偏移"
    assert re.search(r"差值|相减|抵消|两个|两点|T_out\s*[−-]\s*T_in", explanation), (
        "未说明温差来自相减"
    )
    assert re.search(r"无需|不能|不(?:加|添加|套用|应用|需要)", explanation), (
        "未解释温差不能添加绝对温度偏移"
    )


def missing_check(result: dict) -> None:
    assert result["status"] == "needs_input", result["status"]
    assert not outputs(result, "calc_heat_duty"), "缺参时仍执行了显热计算"
    assert "比热" in result["answer"], "未请求缺少的比热参数"


def invalid_check(result: dict) -> None:
    assert result["status"] in {"needs_input", "failed", "out_of_scope"}, result["status"]
    assert not outputs(result, "convert_units"), "不兼容量纲仍换算成功"
    assert "量纲" in result["answer"] or "不能" in result["answer"], "未说明换算失败原因"


def recovery_summary(result: dict) -> dict:
    # Each request repeats earlier errors. Take the maximum count in a single
    # history, so one blocked batch is not counted again on every later request.
    def maximum_history_count(marker: str) -> int:
        return max(
            (
                sum(
                    message_text(message).count(marker)
                    for message in request["messages"]
                    if message.get("role") != "system"
                )
                for request in result.get("model_requests", [])
            ),
            default=0,
        )

    blocked = maximum_history_count(_BATCH_ERROR)
    failed_final = maximum_history_count(_FINAL_ERROR)
    failed_calls = [call for call in result["calls"] if call["status"] == "failed"]
    attempts = blocked + failed_final + len(failed_calls)
    return {
        "blocked_tool_batches": blocked,
        "failed_tool_calls": len(failed_calls),
        "failed_final_answers": failed_final,
        "recovered": bool(attempts and result["status"] == "completed"),
        "count_source": "tool records and errors observed in subsequent model requests",
    }


def check_backend(result: dict, requested: str) -> list[str]:
    backends = [
        call["output"]["retrieval"]["metadata"]["backend"]
        for call in successful_calls(result, "search_knowledge")
    ]
    if requested != "auto":
        assert all(backend == requested for backend in backends), "实际检索后端与本次验收选择不符"
    return backends


def code_identity(root: Path) -> dict:
    """Bind acceptance evidence to the commit and files actually evaluated."""
    digest = hashlib.sha256()
    paths = [root / "pyproject.toml", root / "uv.lock", root / "scripts" / "validate_live.py"]
    paths.extend((root / "src").rglob("*.py"))
    files = 0
    for path in sorted(paths):
        if not path.is_file() or path.is_symlink():
            continue
        for content in (path.relative_to(root).as_posix().encode(), path.read_bytes()):
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        files += 1
    commit = None
    dirty = None
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=5
        )
        if revision.returncode == 0:
            commit = revision.stdout.strip()
        if status.returncode == 0:
            dirty = bool(status.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"commit": commit, "dirty": dirty, "source_sha256": digest.hexdigest(), "files": files}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="真实模型验收；消耗 API 额度")
    parser.add_argument(
        "--index-root",
        type=Path,
        help="复用已就绪索引的项目目录（含 build/lightrag 和 .local）；代码、资料与 runs 使用当前项目",
    )
    parser.add_argument("--backend", choices=("auto", "lexical", "lightrag"), default="auto")
    args = parser.parse_args(argv)
    settings, index_state = prepare_settings(Settings.load(ROOT), args.index_root, args.backend)
    examples = {
        example["id"]: example["question"]
        for example in json.loads((ROOT / "examples/tasks.json").read_text())
    }
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live",
        "model": settings.model,
        "tested_code": code_identity(ROOT),
        "requested_backend": args.backend,
        "index_state": index_state["state"],
        "knowledge_version": KnowledgeBase(settings.knowledge_dir).version,
        "status": "running",
        "cases": [],
    }
    report_path = settings.runs_dir / "live_validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.chmod(0o600)

    def run(case_id, question, check, history=None):
        result = run_task(question, settings, history=history)
        entry = {
            "case": case_id,
            "run_id": result["run_id"],
            "status": result["status"],
            "recovery": recovery_summary(result),
            "model_request_count": len(result["model_requests"]),
            "answer_source": result.get("answer_source", "model"),
        }
        try:
            entry["retrieval_backends"] = check_backend(result, args.backend)
            check(result)
            entry["passed"] = True
        except (AssertionError, KeyError, IndexError, TypeError, ValueError) as exc:
            entry.update(passed=False, error=str(exc) or "验收条件未满足")
        report["cases"].append(entry)
        save()
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        return result

    save()
    run("knowledge", examples["knowledge"], knowledge_check)
    run("heat", examples["heat"], lambda result: check_heat(result, 1000 / 3600 * 4.18 * 40))
    run(
        "heat_changed_input",
        examples["heat"].replace("1000", "2000"),
        lambda result: check_heat(result, 2000 / 3600 * 4.18 * 40),
    )
    run("balance", examples["balance"], balance_check)
    run("units", examples["units"], unit_check)
    missing = run("missing_parameter", examples["missing"], missing_check)
    run(
        "follow_up",
        "比热为4.18 kJ/(kg·K)，假设单相、恒比热、无相变且忽略热损失。",
        lambda result: check_heat(result, 1000 / 3600 * 4.18 * 40),
        history=[
            {"role": "user", "content": examples["missing"]},
            {"role": "assistant", "content": missing["answer"]},
        ],
    )
    run("incompatible_units", "请把5 kg换算为K。", invalid_check)
    run(
        "mixed_heat",
        "稳态、无反应、无积累、充分混合条件下，100 kg/h、盐质量分数5%的溶液与400 kg/h"
        "纯水混合。请检索依据，先求总流量和盐质量分数，再将混合总流量换算成kg/s，"
        "最后计算从25℃加热至65℃的显热负荷。混合液比热明确给定4.18 kJ/(kg·K)，"
        "假设单相、恒比热、无相变、忽略热损失。换算及加热均须引用前序实际工具结果。",
        mixed_heat_check,
    )
    run(
        "temperature_explanation",
        "请把25℃换成K，并解释绝对温度与温差的区别及为什么温差换算不能套用绝对温度的偏移。",
        temperature_explanation_check,
    )
    report["passed"] = all(case["passed"] for case in report["cases"])
    report["status"] = "finished"
    report["recovered_cases"] = sum(case["recovery"]["recovered"] for case in report["cases"])
    report["model_request_count"] = sum(case["model_request_count"] for case in report["cases"])
    save()
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
