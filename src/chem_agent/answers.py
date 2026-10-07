"""Render completed numeric answers from successful, recorded tool outputs."""

from __future__ import annotations

import math
import re
import unicodedata


def _number(value: float) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("计算答复需要有限的工具数值。")
    return format(value, ".12g")


def calculation_answer(calls: list[dict]) -> str | None:
    """Keep rounding out of arithmetic and include the tool's full assumptions.

    This renders existing results only. It does not recompute, infer missing
    inputs, or parse the model's prose to manufacture calculation evidence.
    """
    results: list[str] = []
    inputs: list[str] = []
    conversions: list[str] = []
    assumptions: list[str] = []
    for call in calls:
        if call["status"] != "succeeded":
            continue
        tool = call["tool_name"]
        if tool not in {"convert_units", "calc_heat_duty", "calc_mass_balance"}:
            continue
        output = call["output"]
        if tool == "convert_units":
            conversions.append(
                f"- 单位换算：{_number(output['from_value'])} {output['from_unit']}"
                f" → {_number(output['value'])} {output['unit']}。"
            )
        elif tool == "calc_heat_duty":
            duty = output["heat_duty_kw"]
            direction = "加热" if duty > 0 else "冷却" if duty < 0 else "零热负荷"
            results.append(f"- 显热热负荷：{_number(duty)} kW（{direction}）。")
            values = output["inputs"]
            inputs.extend(
                [
                    f"- 显热计算输入：质量流量 {_number(values['mass_flow_kg_s'])} kg/s；"
                    f"比热 {_number(values['specific_heat_kj_kg_k'])} kJ/(kg·K)；"
                    f"温差 {_number(values['delta_t_k'])} K。",
                    "- 显热公式：Q = m × cp × ΔT；使用未舍入的输入计算热负荷。",
                ]
            )
        else:
            results.extend(
                [
                    f"- 混合后总流量：{_number(output['total_flow_kg_h'])} kg/h。",
                    f"- 目标组分质量流量：{_number(output['component_flow_kg_h'])} kg/h。",
                    f"- 目标组分质量分数：{_number(output['mass_fraction'])}"
                    f"（{_number(output['mass_fraction'] * 100)}%）。",
                ]
            )
            for index, stream in enumerate(call["arguments"]["streams"], 1):
                inputs.append(
                    f"- 混合流股 {index}：{_number(stream['flow_kg_h'])} kg/h；"
                    f"目标组分质量分数 {_number(stream['mass_fraction'])}。"
                )
            inputs.append("- 混合公式：总流量 F = ΣF_j；目标组分质量分数 w = Σ(F_j × w_j) / F。")
        for assumption in output.get("assumptions", []):
            if assumption not in assumptions:
                assumptions.append(assumption)
    if not results and not conversions:
        return None
    lines = ["计算结果：", *(results or conversions)]
    if inputs or (results and conversions):
        lines.extend(["", "计算输入与方法：", *conversions, *inputs])
    if assumptions:
        lines.extend(["", "适用条件：", *(f"- {item}。" for item in assumptions)])
    lines.extend(["", "展示最多保留 12 位有效数字；计算使用工具记录中的未舍入数值。"])
    return "\n".join(lines)


def calculation_explanation(
    text: str, calls: list[dict], evidence: list[dict], citations: list[str]
) -> str:
    """Preserve concept explanations; quantitative prose must be an actual quote.

    This checks expression forms and literal source membership, not the semantic
    truth of arbitrary prose. The computed result remains in calculation_answer.
    """
    text = text.strip()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    inspected = re.sub(
        r"\d{4}-\d{1,2}-\d{1,2}|\d{4}年|第\s*\d+\s*(?:章|节|版|条|页)",
        "引用位置",
        normalized,
    )
    numeric_relations = any(
        re.search(r"\d", statement)
        for statement in re.findall(r"[^\n。；]*[=≈×÷≤≥][^\n。；]*", inspected)
    )
    numeric_operations = re.search(r"\d\s*[*+/×÷⋅·−]\s*[-+]?\d", inspected)
    units = {
        "kw",
        "w",
        "kilowatt",
        "kilowatts",
        "watt",
        "watts",
        "千瓦",
        "瓦特",
        "瓦",
        "kg/h",
        "kg/s",
        "kg/min",
        "kg",
        "g",
        "t",
        "lb",
        "千克",
        "公斤",
        "克",
        "吨",
        "pa",
        "kpa",
        "mpa",
        "bar",
        "atm",
        "psi",
        "帕",
        "千帕",
        "兆帕",
        "巴",
        "k",
        "degc",
        "degf",
        "°c",
        "°f",
        "摄氏度",
        "华氏度",
        "开尔文",
        "%",
        "百分比",
        "kj",
        "j",
        "千焦",
        "焦耳",
    }
    units.update(
        unicodedata.normalize("NFKC", call["output"]["unit"]).casefold()
        for call in calls
        if call["status"] == "succeeded" and call["tool_name"] == "convert_units"
    )
    numerical_quantity = any(
        re.search(rf"\d\s*{re.escape(unit)}(?![a-z])", inspected) for unit in units
    )
    numeric_result = re.search(
        r"(?:热负荷|加热负荷|质量分数|质量流量|总流量|组分流量|比热容?|温差|换算结果)"
        r"[^。；\n\d]{0,24}\d",
        inspected,
    )
    if numeric_relations or numeric_operations or numerical_quantity or numeric_result:
        source = next(
            (hit for hit in evidence if hit["chunk_id"] in citations and text in hit["text"]), None
        )
        if source is None:
            raise ValueError(
                "补充说明请解释概念，不重复数值计算、数值结果或等式；"
                "需要定量知识说明时，使用本轮已引用片段中的逐字原文。"
            )
        return f"\n\n来源原文（{source['chunk_id']}；非本轮计算结果）：\n\n> " + text.replace(
            "\n", "\n> "
        )
    return "\n\n补充说明：\n" + text
