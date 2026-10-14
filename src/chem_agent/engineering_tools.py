"""Executable engineering examples using explicit, user-supplied quantities."""

from __future__ import annotations

from typing import Any

from chem_agent.calculations import _finite_number


def calc_temperature_change(
    inlet_temperature_c: float, outlet_temperature_c: float
) -> dict[str, Any]:
    """Calculate signed Celsius-to-Kelvin temperature difference."""
    inlet = _finite_number(inlet_temperature_c, "inlet_temperature_c")
    outlet = _finite_number(outlet_temperature_c, "outlet_temperature_c")
    if inlet < -273.15 or outlet < -273.15:
        raise ValueError("inlet_temperature_c 和 outlet_temperature_c 均须不低于绝对零度 -273.15℃")
    delta = _finite_number(outlet - inlet, "delta_t_k 计算结果")
    return {
        "delta_t_k": delta,
        "inputs": {"inlet_temperature_c": inlet, "outlet_temperature_c": outlet},
        "assumptions": [
            "输入为摄氏温度；温差 ΔT = 出口温度 − 入口温度，结果单位 K",
            "正值表示升温，负值表示降温；温差供下游计算使用",
        ],
    }


def calc_volume_flow(mass_flow_kg_h: float, density_kg_m3: float) -> dict[str, Any]:
    """Convert mass flow to volume flow using the supplied density."""
    flow = _finite_number(mass_flow_kg_h, "mass_flow_kg_h")
    density = _finite_number(density_kg_m3, "density_kg_m3")
    if flow < 0:
        raise ValueError("mass_flow_kg_h 质量流量必须大于或等于 0")
    if density <= 0:
        raise ValueError("density_kg_m3 密度必须大于 0")
    volume_flow = _finite_number(flow / density, "volume_flow_m3_h 计算结果")
    return {
        "volume_flow_m3_h": volume_flow,
        "inputs": {"mass_flow_kg_h": flow, "density_kg_m3": density},
        "assumptions": [
            "体积流量 V̇ = 质量流量 / 密度，结果单位 m³/h",
            "密度由用户或有来源的数据明确给定，并适用于当前物料与工况",
        ],
    }


def calc_split_flow(total_flow_kg_h: float, split_fraction: float) -> dict[str, Any]:
    """Calculate a conserved, two-way mass-flow split."""
    flow = _finite_number(total_flow_kg_h, "total_flow_kg_h")
    fraction = _finite_number(split_fraction, "split_fraction")
    if flow < 0:
        raise ValueError("total_flow_kg_h 总质量流量必须大于或等于 0")
    if not 0 <= fraction <= 1:
        raise ValueError("split_fraction 分流比例必须在 0 到 1 之间；30% 应输入 0.3")
    branch = _finite_number(flow * fraction, "branch_flow_kg_h 计算结果")
    remainder = _finite_number(flow - branch, "remainder_flow_kg_h 计算结果")
    return {
        "branch_flow_kg_h": branch,
        "remainder_flow_kg_h": remainder,
        "split_fraction": fraction,
        "inputs": {"total_flow_kg_h": flow, "split_fraction": fraction},
        "assumptions": [
            "稳态、无积累、无泄漏的两路分流；分支质量流量 = 总质量流量 × 分流比例",
            "其余质量流量 = 总质量流量 − 分支质量流量；两路结果单位 kg/h",
            "分流比例表示流量比例；均匀物料分流时各路组成保持一致",
        ],
    }


def calc_residence_time(vessel_volume_m3: float, volume_flow_m3_h: float) -> dict[str, Any]:
    """Calculate nominal residence time from effective volume and volume flow."""
    volume = _finite_number(vessel_volume_m3, "vessel_volume_m3")
    flow = _finite_number(volume_flow_m3_h, "volume_flow_m3_h")
    if volume <= 0:
        raise ValueError("vessel_volume_m3 有效持液体积必须大于 0")
    if flow <= 0:
        raise ValueError("volume_flow_m3_h 体积流量必须大于 0")
    hours = _finite_number(volume / flow, "residence_time_h 计算结果")
    minutes = _finite_number(hours * 60, "residence_time_min 计算结果")
    return {
        "residence_time_h": hours,
        "residence_time_min": minutes,
        "inputs": {"vessel_volume_m3": volume, "volume_flow_m3_h": flow},
        "assumptions": [
            "稳态、恒定体积流量；名义停留时间 τ = 有效持液体积 / 体积流量",
            "采用用户给定的有效持液体积与当前工况体积流量，输出 h 和 min",
        ],
    }


def calc_heating_energy(heat_duty_kw: float, duration_h: float) -> dict[str, Any]:
    """Integrate constant signed heat duty over a supplied duration."""
    duty = _finite_number(heat_duty_kw, "heat_duty_kw")
    duration = _finite_number(duration_h, "duration_h")
    if duration < 0:
        raise ValueError("duration_h 持续时间必须大于或等于 0")
    energy_kwh = _finite_number(duty * duration, "energy_kwh 计算结果")
    energy_kj = _finite_number(energy_kwh * 3600, "energy_kj 计算结果")
    return {
        "energy_kwh": energy_kwh,
        "energy_kj": energy_kj,
        "inputs": {"heat_duty_kw": duty, "duration_h": duration},
        "assumptions": [
            "恒定热功率；传热量 E = 热负荷 × 持续时间，1 kWh = 3600 kJ",
            "正值表示加热传入能量，负值表示冷却移出能量；结果保留热负荷符号",
            "热负荷采用对应工况的给定值或已成功计算的工具结果",
        ],
    }


EXTRA_TOOL_FUNCTIONS = {
    "calc_temperature_change": calc_temperature_change,
    "calc_volume_flow": calc_volume_flow,
    "calc_split_flow": calc_split_flow,
    "calc_residence_time": calc_residence_time,
    "calc_heating_energy": calc_heating_energy,
}

EXTRA_TOOL_DESCRIPTIONS = {
    "calc_temperature_change": '计算温差。arguments={"inlet_temperature_c":25,"outlet_temperature_c":65}，输入单位℃且不低于-273.15℃，返回 delta_t_k(K)、inputs、assumptions。下游温差引用 {"$ref":"s2.delta_t_k"}。',
    "calc_volume_flow": '根据给定密度计算体积流量。arguments={"mass_flow_kg_h":{"$ref":"s2.total_flow_kg_h"},"density_kg_m3":1000}，质量流量>=0(kg/h)，密度>0(kg/m³)，返回 volume_flow_m3_h(m³/h)、inputs、assumptions。密度须明确给定且适用当前工况。',
    "calc_split_flow": '稳态两路分流。arguments={"total_flow_kg_h":{"$ref":"s2.total_flow_kg_h"},"split_fraction":0.3}，总流量>=0(kg/h)，流量比例0..1，返回 branch_flow_kg_h、remainder_flow_kg_h(均为kg/h)、split_fraction、inputs、assumptions。',
    "calc_residence_time": '计算名义停留时间。arguments={"vessel_volume_m3":1,"volume_flow_m3_h":{"$ref":"s3.volume_flow_m3_h"}}，有效持液体积>0(m³)，体积流量>0(m³/h)，返回 residence_time_h(h)、residence_time_min(min)、inputs、assumptions。',
    "calc_heating_energy": '恒定热功率下计算传热量。arguments={"heat_duty_kw":{"$ref":"s4.heat_duty_kw"},"duration_h":2}，热负荷(kW)可负表示冷却，时长>=0(h)，返回 energy_kwh(kWh)、energy_kj(kJ)、inputs、assumptions。',
}

EXTRA_TOOL_METADATA = [
    {
        "name": "calc_temperature_change",
        "title": "温差计算",
        "description": "根据明确的入口与出口摄氏温度计算带符号温差。",
        "algorithm": "ΔT = T_out − T_in",
        "capability_kind": "engineering_example",
        "example": {"inlet_temperature_c": 25, "outlet_temperature_c": 65},
    },
    {
        "name": "calc_volume_flow",
        "title": "体积流量计算",
        "description": "用给定工况密度将质量流量换算为体积流量。",
        "algorithm": "V̇ = ṁ / ρ",
        "capability_kind": "engineering_example",
        "example": {"mass_flow_kg_h": 500, "density_kg_m3": 1000},
    },
    {
        "name": "calc_split_flow",
        "title": "两路分流计算",
        "description": "由总流量与分流比例计算分支及其余流量。",
        "algorithm": "F_branch = F_total × α; F_remainder = F_total − F_branch",
        "capability_kind": "engineering_example",
        "example": {"total_flow_kg_h": 500, "split_fraction": 0.3},
    },
    {
        "name": "calc_residence_time",
        "title": "名义停留时间",
        "description": "由有效持液体积与稳态体积流量计算名义停留时间。",
        "algorithm": "τ = V / V̇",
        "capability_kind": "engineering_example",
        "example": {"vessel_volume_m3": 1, "volume_flow_m3_h": 0.5},
    },
    {
        "name": "calc_heating_energy",
        "title": "恒定功率传热量",
        "description": "由恒定热负荷和持续时间计算带符号传热量。",
        "algorithm": "E_kWh = Q_kW × t_h; E_kJ = 3600 × E_kWh",
        "capability_kind": "engineering_example",
        "example": {"heat_duty_kw": 23.222, "duration_h": 2},
    },
]
