"""Shared executable business-tool catalog for the Agent and registry UI."""

from typing import Literal

from chem_agent.calculations import calc_heat_duty, calc_mass_balance, convert_units
from chem_agent.engineering_tools import EXTRA_TOOL_FUNCTIONS, EXTRA_TOOL_METADATA

ToolName = Literal[
    "search_knowledge",
    "convert_units",
    "calc_heat_duty",
    "calc_mass_balance",
    "calc_temperature_change",
    "calc_volume_flow",
    "calc_split_flow",
    "calc_residence_time",
    "calc_heating_energy",
]
MAX_PLAN_STEPS = 10
MAX_TOOL_ATTEMPTS = 20
AGENT_TOOLS = [
    {
        "name": "search_knowledge",
        "title": "化工知识检索",
        "description": "检索知识片段与实体关系。",
        "algorithm": "图谱与向量混合检索 / 字符TF-IDF",
        "capability_kind": "knowledge",
    },
    {
        "name": "convert_units",
        "title": "单位换算",
        "description": "换算兼容量纲的常用单位。",
        "algorithm": "量纲校验与单位归一化",
        "capability_kind": "calculation",
        "example": {"value": 500, "from_unit": "kg/h", "to_unit": "kg/s"},
    },
    {
        "name": "calc_heat_duty",
        "title": "显热负荷计算",
        "description": "根据给定比热、流量和温差计算。",
        "algorithm": "单相恒比热显热衡算 Q = m × cp × ΔT",
        "capability_kind": "calculation",
    },
    {
        "name": "calc_mass_balance",
        "title": "混合物料衡算",
        "description": "计算总流量、组分流量与质量分数。",
        "algorithm": "总质量守恒与组分质量加权求和",
        "capability_kind": "calculation",
    },
    *EXTRA_TOOL_METADATA,
]
TOOL_METADATA = {tool["name"]: tool for tool in AGENT_TOOLS}
TOOL_NAMES = frozenset(TOOL_METADATA)
NUMERIC_FUNCTIONS = {
    "convert_units": convert_units,
    "calc_heat_duty": calc_heat_duty,
    "calc_mass_balance": calc_mass_balance,
    **EXTRA_TOOL_FUNCTIONS,
}
RETRIEVAL_REQUIRED_TOOLS = set(NUMERIC_FUNCTIONS) - {"convert_units", "calc_temperature_change"}
