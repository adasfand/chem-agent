"""Offline regression checks for numerical tools and validation boundaries."""

import math

import pytest

from chem_agent.calculations import calc_heat_duty, calc_mass_balance, convert_units


@pytest.mark.parametrize(
    ("value", "source", "target", "expected"),
    [
        (1000, "kg/h", "kg/s", 1000 / 3600),
        (2, "吨/小时", "kg/s", 2000 / 3600),
        (1, "m³", "L", 1000),
        (60, "升/分钟", "m^3/h", 3.6),
        (1, "MPa", "bar", 10),
        (0, "℃", "K", 273.15),
        (32, "degF", "degC", 0),
        (-40, "°C", "°F", -40),
        (10, "delta_degC", "delta_K", 10),
        (18, "delta_degF", "delta_K", 10),
        (273.15, "K", "摄氏度", 0),
    ],
)
def test_unit_conversions(value, source, target, expected):
    result = convert_units(value, source, target)
    assert result["value"] == pytest.approx(expected, abs=1e-10)
    assert result["unit"] == target
    assert result["from_value"] == value
    assert result["from_unit"] == source


@pytest.mark.parametrize("bad", [True, False, "1", None, math.nan, math.inf, -math.inf])
def test_conversion_rejects_nonfinite_and_nonnumeric_values(bad):
    with pytest.raises(ValueError, match="value"):
        convert_units(bad, "kg", "g")


@pytest.mark.parametrize(
    ("source", "target"),
    [("kg", "L"), ("kg/h", "kg"), ("K", "delta_K"), ("degC", "delta_degC")],
)
def test_conversion_rejects_incompatible_unit_types(source, target):
    with pytest.raises(ValueError, match="不兼容"):
        convert_units(1, source, target)


@pytest.mark.parametrize("unit", ["", None, "kg * 2", "__import__('os').system('true')", "mol"])
def test_conversion_allowlist_rejects_unknown_expressions(unit):
    with pytest.raises(ValueError, match="from_unit"):
        convert_units(1, unit, "kg")


def test_conversion_rejects_temperature_below_absolute_zero():
    with pytest.raises(ValueError, match="绝对零度"):
        convert_units(-274, "degC", "K")


def test_heat_duty_uses_actual_converted_flow():
    flow = convert_units(1000, "kg/h", "kg/s")
    result = calc_heat_duty(flow["value"], 4.18, 40)
    assert result["heat_duty_kw"] == pytest.approx(46.4444444444)
    assert result["inputs"]["mass_flow_kg_s"] == flow["value"]
    assert result["assumptions"]


@pytest.mark.parametrize(("flow", "delta", "expected"), [(2, -20, -167.2), (0, 20, 0), (1, 0, 0)])
def test_heat_duty_supports_cooling_and_zero_duty(flow, delta, expected):
    assert calc_heat_duty(flow, 4.18, delta)["heat_duty_kw"] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("mass_flow_kg_s", -1),
        ("mass_flow_kg_s", True),
        ("mass_flow_kg_s", math.inf),
        ("specific_heat_kj_kg_k", 0),
        ("specific_heat_kj_kg_k", -1),
        ("specific_heat_kj_kg_k", None),
        ("specific_heat_kj_kg_k", math.nan),
        ("delta_t_k", "40"),
        ("delta_t_k", False),
        ("delta_t_k", -math.inf),
    ],
)
def test_heat_duty_validates_inputs(field, bad):
    values = {"mass_flow_kg_s": 1, "specific_heat_kj_kg_k": 4.18, "delta_t_k": 40}
    values[field] = bad
    with pytest.raises(ValueError, match=field):
        calc_heat_duty(**values)


def test_heat_duty_rejects_overflow():
    with pytest.raises(ValueError, match="heat_duty_kw"):
        calc_heat_duty(1e308, 1e308, 10)


def test_calculators_require_key_parameters_and_reject_extra_parameters():
    with pytest.raises(TypeError):
        calc_heat_duty(mass_flow_kg_s=1, delta_t_k=40)
    with pytest.raises(TypeError):
        calc_heat_duty(1, 4.18, 40, pressure=1)


def test_mass_balance_reference_mixture():
    result = calc_mass_balance(
        [
            {"flow_kg_h": 100, "mass_fraction": 0.05},
            {"flow_kg_h": 400, "mass_fraction": 0},
        ]
    )
    assert result["total_flow_kg_h"] == 500
    assert result["component_flow_kg_h"] == 5
    assert result["mass_fraction"] == pytest.approx(0.01)
    assert result["assumptions"]


def test_mass_balance_accepts_zero_flow_and_pure_component():
    result = calc_mass_balance(
        [
            {"flow_kg_h": 0, "mass_fraction": 0.5},
            {"flow_kg_h": 5, "mass_fraction": 1},
        ]
    )
    assert result["mass_fraction"] == 1
    assert result["component_flow_kg_h"] == 5


@pytest.mark.parametrize(
    ("streams", "message"),
    [
        ([], "非空"),
        (None, "非空"),
        ({}, "非空"),
        ([None], r"streams\[0\]"),
        ([{"flow_kg_h": 1}], "缺少字段.*mass_fraction"),
        ([{"mass_fraction": 0.1}], "缺少字段.*flow_kg_h"),
        ([{"flow_kg_h": 1, "mass_fraction": 0.1, "density": 1}], "额外字段.*density"),
        ([{"flow_kg_h": -1, "mass_fraction": 0.1}], "flow_kg_h"),
        ([{"flow_kg_h": 0, "mass_fraction": 0.1}], "总质量流量"),
        ([{"flow_kg_h": True, "mass_fraction": 0.1}], "flow_kg_h"),
        ([{"flow_kg_h": math.inf, "mass_fraction": 0.1}], "flow_kg_h"),
        ([{"flow_kg_h": 1, "mass_fraction": -0.1}], "mass_fraction"),
        ([{"flow_kg_h": 1, "mass_fraction": 5}], "mass_fraction"),
        ([{"flow_kg_h": 1, "mass_fraction": True}], "mass_fraction"),
        ([{"flow_kg_h": 1, "mass_fraction": math.nan}], "mass_fraction"),
    ],
)
def test_mass_balance_rejects_invalid_streams(streams, message):
    with pytest.raises(ValueError, match=message):
        calc_mass_balance(streams)


def test_mass_balance_rejects_overflow():
    with pytest.raises(ValueError, match="流股总流量"):
        calc_mass_balance(
            [
                {"flow_kg_h": 1e308, "mass_fraction": 1},
                {"flow_kg_h": 1e308, "mass_fraction": 1},
            ]
        )
