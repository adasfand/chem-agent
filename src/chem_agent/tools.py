"""Four domain functions; inputs are fixed-unit schemas, independent of Agent."""
import math
from typing import Annotated, Literal

import pint
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def real_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("必须为有限数值，不接受布尔值或数值字符串")
    return value


Number = Annotated[float, BeforeValidator(real_number)]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SearchInput(StrictInput):
    query: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=20, strict=True)


class ConvertInput(StrictInput):
    value: Number
    from_unit: str
    to_unit: str
    quantity_kind: Literal["general", "absolute_temperature", "temperature_difference"] = "general"


class HeatInput(StrictInput):
    mass_flow_kg_s: Number = Field(ge=0)
    cp_kj_kg_k: Number = Field(gt=0)
    delta_t_k: Number


class StreamInput(StrictInput):
    mass_flow_kg_h: Number = Field(ge=0)
    mass_fraction: Number = Field(ge=0, le=1)


class BalanceInput(StrictInput):
    streams: list[StreamInput] = Field(min_length=2, max_length=20)


ureg = pint.UnitRegistry()


def convert_units(data: ConvertInput) -> dict:
    source_unit, target_unit = ureg.Unit(data.from_unit), ureg.Unit(data.to_unit)
    is_temperature = source_unit.dimensionality == ureg.kelvin.dimensionality
    if is_temperature:
        if data.quantity_kind == "general":
            raise ValueError("温度换算须声明 absolute_temperature 或 temperature_difference")
        if data.quantity_kind == "temperature_difference":
            allowed = {"kelvin", "delta_degree_Celsius", "delta_degree_Fahrenheit", "degree_Rankine"}
            if str(source_unit) not in allowed or str(target_unit) not in allowed:
                raise ValueError("温差必须使用 K、delta_degC、delta_degF 或 degR，不能使用绝对摄氏/华氏单位")
        elif "delta_" in str(source_unit) or "delta_" in str(target_unit):
            raise ValueError("绝对温度不能使用delta温差单位")
    elif data.quantity_kind != "general":
        raise ValueError("温度类型标记只能用于纯温度量纲")
    quantity = ureg.Quantity(data.value, data.from_unit).to(data.to_unit)
    value = float(quantity.magnitude)
    if not math.isfinite(value):
        raise ValueError("换算结果超出有限数值范围")
    return {"value": value, "unit": data.to_unit, "quantity_kind": data.quantity_kind,
            "inputs": data.model_dump()}


def calc_heat_duty(data: HeatInput) -> dict:
    value = data.mass_flow_kg_s * data.cp_kj_kg_k * data.delta_t_k
    if not math.isfinite(value):
        raise ValueError("热负荷结果超出有限数值范围")
    return {"heat_duty_kw": value, "unit": "kW", "inputs": data.model_dump(),
            "assumptions": ["单相", "恒比热", "无相变", "忽略热损失"],
            "sign_convention": "升温为正，降温为负；温差用 K，摄氏温差数值相同"}


def calc_mass_balance(data: BalanceInput) -> dict:
    total = sum(s.mass_flow_kg_h for s in data.streams)
    component = sum(s.mass_flow_kg_h * s.mass_fraction for s in data.streams)
    if total <= 0 or not math.isfinite(total) or not math.isfinite(component):
        raise ValueError("总质量流量必须为有限正数")
    return {"total_mass_flow_kg_h": total, "component_mass_flow_kg_h": component,
            "mass_fraction": component / total, "inputs": data.model_dump(),
            "assumptions": ["稳态", "无反应", "无积累", "各股为同一组分的质量分数"]}


SCHEMAS = {"search_knowledge": SearchInput, "convert_units": ConvertInput,
           "calc_heat_duty": HeatInput, "calc_mass_balance": BalanceInput}
FUNCTIONS = {"convert_units": convert_units, "calc_heat_duty": calc_heat_duty,
             "calc_mass_balance": calc_mass_balance}
