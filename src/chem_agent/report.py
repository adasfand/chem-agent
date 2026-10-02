"""Render existing execution evidence as a safe, portable Markdown report."""

from __future__ import annotations

import math
import re
from typing import Any

from chem_agent.trace import redact

_STATUS = {
    "running": "正在处理",
    "completed": "已完成",
    "needs_input": "等待补充参数",
    "no_evidence": "资料不足",
    "failed": "执行未完成",
    "out_of_scope": "超出当前范围",
    "cancelled": "已取消",
    "pending": "待执行",
    "succeeded": "成功",
}
_TOOLS = {
    "search_knowledge": "知识检索",
    "convert_units": "单位换算",
    "calc_heat_duty": "显热热负荷",
    "calc_mass_balance": "混合物料衡算",
}
_SENSITIVE_KEY = re.compile(r"api.?key|secret|password|authorization|token|key_file", re.I)
_LOCAL_PATH = re.compile(
    r"file:(?://)?[^\s<>\"'`|]+"
    r"|(?<![\w:/])(?:[A-Za-z]:[\\/]|\\\\)[^\s<>\"'`|]+"
    r"|(?<![A-Za-z0-9/])/(?:Users|home|private|tmp|var|etc|Volumes|Library|usr|opt|mnt|root|srv)"
    r"(?:/[^\s<>\"'`|]*)?"
    r"|(?<![\w:/<])/(?!/)[^\s<>\"'`|]+",
    re.I,
)


def _records(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _private_values(result: dict) -> tuple[str, ...]:
    values = []

    def collect(value: Any, sensitive: bool = False) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                collect(child, sensitive or bool(_SENSITIVE_KEY.search(str(key))))
        elif isinstance(value, list):
            for child in value:
                collect(child, sensitive)
        elif isinstance(value, str) and value and (sensitive or _LOCAL_PATH.match(value)):
            values.append(value)

    collect(result.get("config", {}))
    path = result.get("trace_path")
    if isinstance(path, str) and path:
        values.append(path)
    return tuple(sorted(set(values), key=len, reverse=True))


def _text(value: Any, secrets: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        return ""
    value = redact(value, secrets)
    value = _LOCAL_PATH.sub("[本地路径已隐藏]", value)
    # Preserve ordinary newlines; remove controls that can obscure exported text.
    return "".join(char for char in value if char in "\n\t" or ord(char) >= 32).strip()


def _fence(text: str) -> str:
    size = max([2, *(len(match[0]) for match in re.finditer(r"`+", text))]) + 1
    delimiter = "`" * size
    return f"{delimiter}text\n{text}\n{delimiter}"


def _inline(text: str) -> str:
    text = " ".join(text.split()).replace("\\", "\\\\").replace("|", r"\|")
    size = max([0, *(len(match[0]) for match in re.finditer(r"`+", text))]) + 1
    delimiter = "`" * size
    return f"{delimiter} {text or '—'} {delimiter}"


def _number(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not math.isfinite(value):
            return None
    except OverflowError:
        return None
    return format(value, ".12g")


def _metrics(call: dict) -> list[tuple[str, str, str]]:
    output = call.get("output")
    if call.get("status") != "succeeded" or not isinstance(output, dict):
        return []
    rows = []

    def add(label: str, value: Any, unit: Any) -> None:
        number = _number(value)
        if number is not None and isinstance(unit, str) and unit.strip():
            rows.append((label, number, unit))

    if call.get("tool_name") == "convert_units":
        add("换算前", output.get("from_value"), output.get("from_unit"))
        add("换算结果", output.get("value"), output.get("unit"))
    elif call.get("tool_name") == "calc_heat_duty":
        add("热负荷", output.get("heat_duty_kw"), "kW")
        inputs = output.get("inputs")
        if isinstance(inputs, dict):
            add("质量流量", inputs.get("mass_flow_kg_s"), "kg/s")
            add("给定比热", inputs.get("specific_heat_kj_kg_k"), "kJ/(kg·K)")
            add("温差", inputs.get("delta_t_k"), "K")
    elif call.get("tool_name") == "calc_mass_balance":
        add("混合后总流量", output.get("total_flow_kg_h"), "kg/h")
        add("组分质量流量", output.get("component_flow_kg_h"), "kg/h")
        add("组分质量分数", output.get("mass_fraction"), "1（质量分数，0–1）")
    return rows


def render_report(result: dict) -> str:
    """Export recorded results, without model calls, file access, or mutation.

    Free-form content stays in literal Markdown fences/code spans. Only known
    numeric output fields of successful tools become result rows; an answer is
    preserved as an answer and is never parsed to manufacture calculation data.
    """
    if not isinstance(result, dict):
        raise ValueError("运行报告需要提供运行记录对象。")
    secrets = _private_values(result)

    def safe(value: Any, fallback: str = "未记录") -> str:
        return _text(value, secrets) or fallback

    lines = [
        "# 化工任务运行报告",
        "",
        f"- 运行编号：{_inline(safe(result.get('run_id')))}",
        f"- 状态：{_STATUS.get(result.get('status'), '未知状态')}",
    ]
    for field, label in (
        ("started_at", "开始时间"),
        ("finished_at", "结束时间"),
        ("knowledge_version", "知识资料版本"),
    ):
        if isinstance(result.get(field), str) and result[field]:
            lines.append(f"- {label}：{_inline(safe(result[field]))}")
    warning = _text(result.get("record_warning"), secrets)
    if warning:
        lines.extend(
            [
                "",
                "## 记录保存提示",
                "",
                "本地运行记录未成功保存；本报告根据当前内存中的运行记录生成。",
                "",
                _fence(warning),
            ]
        )
    lines.extend(
        [
            "",
            "## 用户问题",
            "",
            _fence(safe(result.get("question"), "未记录用户问题。")),
        ]
    )
    parent_run_id = _text(result.get("parent_run_id"), secrets)
    user_history = [
        _text(item.get("content"), secrets)
        for item in _records(result.get("history"))
        if item.get("role") == "user"
        and isinstance(item.get("content"), str)
        and item["content"].strip()
    ][-4:]
    if parent_run_id or user_history:
        lines.extend(["", "## 关联上下文", ""])
        if parent_run_id:
            lines.append(f"- 前序运行编号：{_inline(parent_run_id)}")
        if user_history:
            lines.extend(["", "以下为最近的用户输入，按原始顺序列出（最多 4 条）。"])
            for index, content in enumerate(user_history, 1):
                lines.extend(["", f"### 先前输入 {index}", "", _fence(content)])
        else:
            lines.extend(["", "未记录可展示的先前用户输入。"])
    lines.extend(
        [
            "",
            "## 答复",
            "",
            _fence(safe(result.get("answer"), "尚未记录答复。")),
            "",
            "## 实际工具结果",
            "",
        ]
    )
    calls = _records(result.get("calls"))
    succeeded = [call for call in calls if call.get("status") == "succeeded"]
    lines.append(f"记录中有 {len(succeeded)} 次成功工具调用。以下数值仅取自成功调用的输出。")
    numeric_rows = []
    assumptions = []
    for call in succeeded:
        tool = _TOOLS.get(call.get("tool_name"), "其他工具")
        for label, value, unit in _metrics(call):
            numeric_rows.append(
                "| "
                + " | ".join(
                    _inline(safe(item)) for item in (call.get("step_id"), tool, label, value, unit)
                )
                + " |"
            )
        output = call.get("output")
        if call.get("tool_name") in {"calc_heat_duty", "calc_mass_balance"} and isinstance(
            output, dict
        ):
            raw_assumptions = output.get("assumptions")
            if isinstance(raw_assumptions, list):
                for assumption in raw_assumptions:
                    text = _text(assumption, secrets)
                    if text and text not in assumptions:
                        assumptions.append(text)
    if numeric_rows:
        lines.extend(
            [
                "",
                "| 步骤 | 工具 | 指标 | 数值 | 单位 |",
                "| --- | --- | --- | --- | --- |",
                *numeric_rows,
                "",
                "数值最多显示 12 位有效数字；质量分数使用 0–1 口径。",
            ]
        )
    else:
        lines.extend(["", "本次记录没有可展示的成功数值计算结果。"])

    failed = [call for call in calls if call.get("status") == "failed"]
    if failed:
        lines.extend(["", "### 失败调用", ""])
        for call in failed:
            lines.append(
                _fence(
                    f"步骤：{safe(call.get('step_id'))}\n"
                    f"工具：{_TOOLS.get(call.get('tool_name'), '其他工具')}\n"
                    f"原因：{safe(call.get('error'), '未记录具体原因。')}"
                )
            )
            lines.append("")

    lines.extend(["", "## 执行计划", ""])
    plan = _records(result.get("plan"))
    if plan:
        lines.extend(["| 步骤 | 目标 | 工具 | 状态 |", "| --- | --- | --- | --- |"])
        for step in plan:
            cells = (
                safe(step.get("step_id")),
                safe(step.get("goal")),
                _TOOLS.get(step.get("tool_name"), "其他工具"),
                _STATUS.get(step.get("status"), "未知状态"),
            )
            lines.append("| " + " | ".join(_inline(cell) for cell in cells) + " |")
    else:
        lines.append("本次记录未登记执行计划。")

    lines.extend(["", "## 知识依据", ""])
    citations = result.get("citations")
    cited = (
        {item for item in citations if isinstance(item, str)}
        if isinstance(citations, list)
        else set()
    )
    evidence = []
    seen = set()
    for hit in _records(result.get("evidence")):
        chunk_id = hit.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            evidence.append(hit)
    if not evidence:
        lines.append("本次记录没有检索依据。")
    for index, hit in enumerate(evidence, 1):
        label = "实际引用" if hit["chunk_id"] in cited else "仅检索，未引用"
        excerpt = safe(hit.get("text"), "未记录片段正文。")
        if len(excerpt) > 280:
            excerpt = excerpt[:280] + "…（摘录已截断）"
        lines.extend(
            [
                f"### 依据 {index} · {label}",
                "",
                _fence(
                    f"标题：{safe(hit.get('title'))}\n"
                    f"编号：{safe(hit['chunk_id'])}\n"
                    f"来源：{safe(hit.get('source'), '来源未注明')}\n\n{excerpt}"
                ),
                "",
            ]
        )
    if cited - seen:
        lines.append(f"有 {len(cited - seen)} 个引用编号未出现在检索记录中，未将其列为有效依据。")

    lines.extend(
        [
            "",
            "## 适用边界",
            "",
            "支持常用单位换算、单相恒比热显热计算及稳态无反应混合衡算。物性需明确给定；知识卡是教学说明。",
            "",
            "报告展示已有记录；失败或未执行的步骤不构成成功计算结果。",
        ]
    )
    if assumptions:
        lines.extend(["", "### 本次计算的工具假设", "", _fence("\n".join(assumptions))])
    return "\n".join(lines).strip() + "\n"
