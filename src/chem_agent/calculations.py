"""Deterministic calculations with explicit units and no model dependencies."""

from __future__ import annotations

import math
from typing import Any

import pint

_UNITS = pint.UnitRegistry()

# Only these spellings reach Pint; user text is never evaluated as an expression.
_UNIT_GROUPS: dict[str, dict[str, str]] = {
    "mass": {
        "mg": "milligram",
        "g": "gram",
        "kg": "kilogram",
        "t": "metric_ton",
        "lb": "pound",
    },
    "volume": {
        "m3": "meter ** 3",
        "cm3": "centimeter ** 3",
        "L": "liter",
        "mL": "milliliter",
    },
    "mass_flow": {
        "kg/s": "kilogram / second",
        "kg/min": "kilogram / minute",
        "kg/h": "kilogram / hour",
        "g/s": "gram / second",
        "g/min": "gram / minute",
        "g/h": "gram / hour",
        "t/h": "metric_ton / hour",
        "t/d": "metric_ton / day",
        "lb/h": "pound / hour",
    },
    "volume_flow": {
        "m3/s": "meter ** 3 / second",
        "m3/min": "meter ** 3 / minute",
        "m3/h": "meter ** 3 / hour",
        "L/s": "liter / second",
        "L/min": "liter / minute",
        "L/h": "liter / hour",
        "mL/s": "milliliter / second",
        "mL/min": "milliliter / minute",
        "mL/h": "milliliter / hour",
    },
    "pressure": {
        "Pa": "pascal",
        "kPa": "kilopascal",
        "MPa": "megapascal",
        "bar": "bar",
        "atm": "atmosphere",
        "psi": "psi",
    },
    "temperature": {
        "K": "kelvin",
        "degC": "degC",
        "degF": "degF",
    },
    "temperature_difference": {
        "delta_K": "kelvin",
        "delta_degC": "delta_degC",
        "delta_degF": "delta_degF",
    },
}
_UNIT_ALIASES = {
    "毫克": "mg",
    "克": "g",
    "千克": "kg",
    "公斤": "kg",
    "吨": "t",
    "磅": "lb",
    "立方米": "m3",
    "立方厘米": "cm3",
    "升": "L",
    "毫升": "mL",
    "l": "L",
    "ml": "mL",
    "帕": "Pa",
    "帕斯卡": "Pa",
    "千帕": "kPa",
    "兆帕": "MPa",
    "巴": "bar",
    "标准大气压": "atm",
    "开尔文": "K",
    "摄氏度": "degC",
    "℃": "degC",
    "°C": "degC",
    "C": "degC",
    "华氏度": "degF",
    "℉": "degF",
    "°F": "degF",
    "F": "degF",
    "ΔK": "delta_K",
    "温差K": "delta_K",
    "Δ°C": "delta_degC",
    "Δ℃": "delta_degC",
    "温差℃": "delta_degC",
    "Δ°F": "delta_degF",
    "Δ℉": "delta_degF",
}
_FLOW_ALIASES = {
    "千克": "kg",
    "公斤": "kg",
    "克": "g",
    "吨": "t",
    "磅": "lb",
    "立方米": "m3",
    "升": "L",
    "毫升": "mL",
}
_TIME_ALIASES = {"秒": "s", "分钟": "min", "分": "min", "小时": "h", "时": "h", "天": "d"}
for _numerator, _canonical in _FLOW_ALIASES.items():
    for _denominator, _time in _TIME_ALIASES.items():
        _UNIT_ALIASES[f"{_numerator}/{_denominator}"] = f"{_canonical}/{_time}"
        _UNIT_ALIASES[f"{_numerator}每{_denominator}"] = f"{_canonical}/{_time}"
_SUPPORTED_UNITS = {
    spelling: (group, expression)
    for group, entries in _UNIT_GROUPS.items()
    for spelling, expression in entries.items()
}


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} 必须是有限数值，不能是布尔值或字符串")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field} 超出可表示的有限数值范围") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} 必须是有限数值，不能是 NaN 或无穷大")
    return number


def _resolve_unit(unit: str, field: str) -> tuple[str, str]:
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError(f"{field} 必须提供非空单位字符串")
    normalized = "".join(unit.split()).replace("³", "3").replace("^3", "3")
    normalized = _UNIT_ALIASES.get(normalized, normalized)
    if normalized not in _SUPPORTED_UNITS:
        raise ValueError(
            f"{field} 不支持单位 {unit!r}；请使用常用质量、体积、流量、压力、温度或温差单位"
        )
    return _SUPPORTED_UNITS[normalized]


def convert_units(value: float, from_unit: str, to_unit: str) -> dict[str, Any]:
    """Convert allowlisted units; temperature differences must use delta units."""
    number = _finite_number(value, "value")
    source_group, source = _resolve_unit(from_unit, "from_unit")
    target_group, target = _resolve_unit(to_unit, "to_unit")
    if source_group != target_group:
        raise ValueError(
            "from_unit 与 to_unit 的量纲或温度类型不兼容；温差请使用 delta_K、delta_degC 或 delta_degF"
        )
    quantity = _UNITS.Quantity(number, source)
    if source_group == "temperature" and quantity.to("kelvin").magnitude < 0:
        raise ValueError("value 对应温度低于绝对零度")
    converted = _finite_number(quantity.to(target).magnitude, "换算结果")
    return {"value": converted, "unit": to_unit, "from_value": number, "from_unit": from_unit}


def calc_heat_duty(
    mass_flow_kg_s: float,
    specific_heat_kj_kg_k: float,
    delta_t_k: float,
) -> dict[str, Any]:
    """Calculate steady sensible heat duty; a negative duty denotes cooling."""
    flow = _finite_number(mass_flow_kg_s, "mass_flow_kg_s")
    heat_capacity = _finite_number(specific_heat_kj_kg_k, "specific_heat_kj_kg_k")
    temperature_change = _finite_number(delta_t_k, "delta_t_k")
    if flow < 0:
        raise ValueError("mass_flow_kg_s 质量流量必须大于或等于 0")
    if heat_capacity <= 0:
        raise ValueError("specific_heat_kj_kg_k 比热必须大于 0，且须由用户或有来源的数据提供")
    duty = _finite_number(flow * heat_capacity * temperature_change, "heat_duty_kw 计算结果")
    return {
        "heat_duty_kw": duty,
        "inputs": {
            "mass_flow_kg_s": flow,
            "specific_heat_kj_kg_k": heat_capacity,
            "delta_t_k": temperature_change,
        },
        "assumptions": [
            "单相、稳态、恒比热的显热计算；Q = 质量流量 × 定压比热 × 温差",
            "无化学反应、无相变；忽略热损失、轴功以及动能、位能变化",
            "比热需明确给定且适用于该温度区间，不由知识卡代填物性",
            "正值表示加热，负值表示冷却；结果单位为 kW",
        ],
    }


def calc_mass_balance(streams: list[dict]) -> dict[str, Any]:
    """Mix streams using mass fractions for the same conserved component."""
    if not isinstance(streams, list) or not streams:
        raise ValueError("streams 必须是非空流股列表")
    flows: list[float] = []
    component_flows: list[float] = []
    required = {"flow_kg_h", "mass_fraction"}
    for index, stream in enumerate(streams):
        prefix = f"streams[{index}]"
        if not isinstance(stream, dict):
            raise ValueError(f"{prefix} 必须是包含 flow_kg_h 和 mass_fraction 的对象")
        missing = required - stream.keys()
        if missing:
            raise ValueError(f"{prefix} 缺少字段：{', '.join(sorted(missing))}")
        extra = stream.keys() - required
        if extra:
            raise ValueError(f"{prefix} 含不支持的额外字段：{', '.join(sorted(map(str, extra)))}")
        flow = _finite_number(stream["flow_kg_h"], f"{prefix}.flow_kg_h")
        fraction = _finite_number(stream["mass_fraction"], f"{prefix}.mass_fraction")
        if flow < 0:
            raise ValueError(f"{prefix}.flow_kg_h 质量流量必须大于或等于 0")
        if not 0 <= fraction <= 1:
            raise ValueError(f"{prefix}.mass_fraction 必须在 0 到 1 之间；1% 应输入 0.01")
        flows.append(flow)
        component_flows.append(flow * fraction)
    try:
        total_flow = _finite_number(math.fsum(flows), "total_flow_kg_h 计算结果")
        component_flow = _finite_number(math.fsum(component_flows), "component_flow_kg_h 计算结果")
    except OverflowError as exc:
        raise ValueError("流股总流量超出可表示的有限数值范围") from exc
    if total_flow <= 0:
        raise ValueError("total_flow_kg_h 总质量流量必须大于 0")
    return {
        "total_flow_kg_h": total_flow,
        "component_flow_kg_h": component_flow,
        "mass_fraction": component_flow / total_flow,
        "assumptions": [
            "稳态、完全混合；无反应、无泄漏、无积累",
            "所有流股的 mass_fraction 指同一守恒组分的质量分数，取值 0 到 1",
            "所有输入及输出质量流量单位为 kg/h",
        ],
    }
