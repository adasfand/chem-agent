"""Server-only checks. These tests have NOT been executed locally."""
import pytest
from pydantic import ValidationError

from chem_agent.tools import (BalanceInput, ConvertInput, HeatInput,
                              calc_heat_duty, calc_mass_balance, convert_units)


def test_heat_reference_and_changed_input():
    flow = convert_units(ConvertInput(value=1000, from_unit="kg/h", to_unit="kg/s"))["value"]
    first = calc_heat_duty(HeatInput(mass_flow_kg_s=flow, cp_kj_kg_k=4.18, delta_t_k=40))
    second = calc_heat_duty(HeatInput(mass_flow_kg_s=flow * 2, cp_kj_kg_k=4.18, delta_t_k=40))
    assert first["heat_duty_kw"] == pytest.approx(46.4444444444)
    assert second["heat_duty_kw"] == pytest.approx(2 * first["heat_duty_kw"])


def test_mixing_reference():
    result = calc_mass_balance(BalanceInput(streams=[
        {"mass_flow_kg_h": 100, "mass_fraction": 0.05},
        {"mass_flow_kg_h": 400, "mass_fraction": 0},
    ]))
    assert result["total_mass_flow_kg_h"] == 500
    assert result["component_mass_flow_kg_h"] == 5
    assert result["mass_fraction"] == pytest.approx(0.01)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "4.18", 0, -1])
def test_invalid_cp(value):
    with pytest.raises(ValidationError):
        HeatInput(mass_flow_kg_s=1, cp_kj_kg_k=value, delta_t_k=40)


def test_invalid_fraction_and_zero_flow():
    with pytest.raises(ValidationError):
        BalanceInput(streams=[{"mass_flow_kg_h": 100, "mass_fraction": 5}] * 2)
    with pytest.raises(ValueError):
        calc_mass_balance(BalanceInput(streams=[{"mass_flow_kg_h": 0, "mass_fraction": 0}] * 2))


def test_dimension_error_and_temperature_semantics():
    import pint
    with pytest.raises(pint.DimensionalityError):
        convert_units(ConvertInput(value=1, from_unit="kg", to_unit="K"))
    with pytest.raises(ValueError):
        convert_units(ConvertInput(value=40, from_unit="degC", to_unit="K", quantity_kind="temperature_difference"))
    result = convert_units(ConvertInput(value=40, from_unit="delta_degC", to_unit="K", quantity_kind="temperature_difference"))
    assert result["value"] == 40
