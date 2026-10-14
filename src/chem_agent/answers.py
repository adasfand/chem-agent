"""Render completed numeric answers from successful, recorded tool outputs."""

from __future__ import annotations

import math
import re
import unicodedata

from chem_agent.tool_catalog import NUMERIC_FUNCTIONS, TOOL_METADATA

EXTRA_METRICS = {
    "calc_temperature_change": [("delta_t_k", "温差", "K")],
    "calc_volume_flow": [("volume_flow_m3_h", "体积流量", "m³/h")],
    "calc_split_flow": [
        ("branch_flow_kg_h", "分支流量", "kg/h"),
        ("remainder_flow_kg_h", "其余流量", "kg/h"),
    ],
    "calc_residence_time": [
        ("residence_time_h", "名义停留时间", "h"),
        ("residence_time_min", "名义停留时间", "min"),
    ],
    "calc_heating_energy": [("energy_kwh", "传热量", "kWh"), ("energy_kj", "传热量", "kJ")],
}
EXTRA_INPUTS = {
    "inlet_temperature_c": ("入口温度", "℃"),
    "outlet_temperature_c": ("出口温度", "℃"),
    "mass_flow_kg_h": ("质量流量", "kg/h"),
    "density_kg_m3": ("密度", "kg/m³"),
    "total_flow_kg_h": ("总质量流量", "kg/h"),
    "split_fraction": ("分流比例", ""),
    "vessel_volume_m3": ("有效持液体积", "m³"),
    "volume_flow_m3_h": ("体积流量", "m³/h"),
    "heat_duty_kw": ("热功率", "kW"),
    "duration_h": ("持续时间", "h"),
}


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
        if tool not in NUMERIC_FUNCTIONS:
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
        elif tool in EXTRA_METRICS:
            results.extend(
                f"- {label}：{_number(output[field])} {unit}。"
                for field, label, unit in EXTRA_METRICS[tool]
            )
            rendered = [
                f"{EXTRA_INPUTS[field][0]} {_number(value)} {EXTRA_INPUTS[field][1]}"
                for field, value in output["inputs"].items()
            ]
            inputs.append(f"- {TOOL_METADATA[tool]['title']}输入：" + "；".join(rendered) + "。")
            inputs.append(f"- 方法：{TOOL_METADATA[tool]['algorithm']}。")
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


def requires_concept_explanation(question: str) -> bool:
    """Recognize explicit explanation requests in trusted user input.

    This is a narrow completion guard, not a semantic intent classifier.
    """
    affirmative = re.sub(r"(?:不要|无需|不需要|不必|不用)(?:再|额外)?(?:解释|说明)", "", question)
    return bool(re.search(r"解释|为什么|为何|区别|原理|含义|理由", affirmative))


def _is_quantitative(text: str, calls: list[dict]) -> bool:
    """Preserve concept explanations; quantitative prose must be an actual quote.

    This checks expression forms and literal source membership, not the semantic
    truth of arbitrary prose. The computed result remains in calculation_answer.
    """
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
        "kwh",
        "m3/h",
        "m3",
        "kg/m3",
        "h",
        "min",
        "s",
        "小时",
        "分钟",
        "秒",
        "立方米",
        "千瓦时",
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
        r"(?:热负荷|加热负荷|质量分数|质量流量|总流量|组分流量|比热容?|温差|换算结果|密度|体积流量|停留时间|传热量|分支流量|其余流量|分流比例|热功率)"
        r"[^。；\n\d]{0,24}\d",
        inspected,
    )
    return bool(numeric_relations or numeric_operations or numerical_quantity or numeric_result)


def calculation_explanation(
    text: str, calls: list[dict], evidence: list[dict], citations: list[str]
) -> str:
    """Validate numeric sentences separately from adjacent concept explanation.

    Literal quotes can come from different cited chunks. This checks expression
    forms and source membership, not the semantic truth of arbitrary prose.
    """
    text = text.strip()
    if not text:
        return ""
    if not _is_quantitative(text, calls):
        return "\n\n补充说明：\n" + text
    sources = [hit for hit in evidence if hit["chunk_id"] in citations]
    whole_source = next((hit for hit in sources if text in hit["text"]), None)
    if whole_source and _is_quantitative(text, calls):
        parts = [text]
    else:
        parts = [part.strip() for part in re.split(r"(?<=[。；！？!?;])|\n+", text) if part.strip()]
    rendered = []
    for part in parts:
        if not _is_quantitative(part, calls):
            rendered.append("\n\n补充说明：\n" + part)
            continue
        source = next((hit for hit in sources if part in hit["text"]), None)
        if source is None:
            raise ValueError(
                f"补充说明中的定量句未匹配本轮已引用片段的逐字原文：{part[:200]}。"
                "请删除该句中的数值，改成概念解释；或者单独复制已引用片段的原句。"
                "计算结果由程序输出，不需要在 explanation 重复。"
            )
        rendered.append(
            f"\n\n来源原文（{source['chunk_id']}；非本轮计算结果）：\n\n> "
            + part.replace("\n", "\n> ")
        )
    return "".join(rendered)
