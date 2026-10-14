"""Offline checks for executable teaching tools and numeric boundaries."""

import inspect
import math

import pytest

from chem_agent.engineering_tools import (
    EXTRA_TOOL_DESCRIPTIONS,
    EXTRA_TOOL_FUNCTIONS,
    EXTRA_TOOL_METADATA,
    calc_heating_energy,
    calc_residence_time,
    calc_split_flow,
    calc_temperature_change,
    calc_volume_flow,
)


def test_engineering_chain_uses_actual_outputs():
    temperature = calc_temperature_change(25, 65)
    volume = calc_volume_flow(500, 1000)
    residence = calc_residence_time(1, volume["volume_flow_m3_h"])
    split = calc_split_flow(500, 0.3)
    energy = calc_heating_energy(23.222, 2)
    assert temperature["delta_t_k"] == 40
    assert volume["volume_flow_m3_h"] == 0.5
    assert residence["residence_time_h"] == 2
    assert residence["residence_time_min"] == 120
    assert split["branch_flow_kg_h"] == 150
    assert split["remainder_flow_kg_h"] == 350
    assert energy["energy_kwh"] == pytest.approx(46.444)
    assert energy["energy_kj"] == pytest.approx(167198.4)


@pytest.mark.parametrize("fraction", [0, 1, 0.3, 1 / 3])
def test_split_preserves_flow_and_handles_endpoints(fraction):
    result = calc_split_flow(500, fraction)
    assert result["branch_flow_kg_h"] + result["remainder_flow_kg_h"] == pytest.approx(500)
    assert result["split_fraction"] == fraction


def test_zero_and_cooling_conditions():
    assert calc_temperature_change(-273.15, -273.15)["delta_t_k"] == 0
    assert calc_temperature_change(70, 20)["delta_t_k"] == -50
    assert calc_volume_flow(0, 1000)["volume_flow_m3_h"] == 0
    assert calc_split_flow(0, 0.5)["branch_flow_kg_h"] == 0
    assert calc_heating_energy(-10, 2)["energy_kwh"] == -20
    assert calc_heating_energy(-10, 2)["energy_kj"] == -72000
    assert calc_heating_energy(1e308, 0)["energy_kj"] == 0


@pytest.mark.parametrize("metadata", EXTRA_TOOL_METADATA)
def test_catalog_examples_are_executable_and_keep_inputs(metadata):
    name = metadata["name"]
    example = metadata["example"]
    result = EXTRA_TOOL_FUNCTIONS[name](**example)
    assert result["inputs"] == example
    assert result["assumptions"]
    assert metadata["capability_kind"] == "engineering_example"
    assert metadata["algorithm"]
    assert "$ref" in EXTRA_TOOL_DESCRIPTIONS[name]


def test_catalog_names_are_consistent():
    assert set(EXTRA_TOOL_FUNCTIONS) == set(EXTRA_TOOL_DESCRIPTIONS)
    assert set(EXTRA_TOOL_FUNCTIONS) == {entry["name"] for entry in EXTRA_TOOL_METADATA}
    assert len(EXTRA_TOOL_METADATA) == 5


INVALID_NUMBERS = [True, False, None, "1", math.nan, math.inf, -math.inf, 10**400]
PARAMETERS = [
    (entry["name"], parameter)
    for entry in EXTRA_TOOL_METADATA
    for parameter in inspect.signature(EXTRA_TOOL_FUNCTIONS[entry["name"]]).parameters
]


@pytest.mark.parametrize(("name", "field"), PARAMETERS)
@pytest.mark.parametrize("bad", INVALID_NUMBERS)
def test_every_parameter_rejects_invalid_numeric_inputs(name, field, bad):
    values = next(dict(entry["example"]) for entry in EXTRA_TOOL_METADATA if entry["name"] == name)
    values[field] = bad
    with pytest.raises(ValueError, match=field):
        EXTRA_TOOL_FUNCTIONS[name](**values)


@pytest.mark.parametrize(
    ("function", "arguments", "message"),
    [
        (calc_temperature_change, [-273.16, 0], "绝对零度"),
        (calc_temperature_change, [0, -273.16], "绝对零度"),
        (calc_volume_flow, [-1, 1000], "mass_flow_kg_h"),
        (calc_volume_flow, [1, 0], "density_kg_m3"),
        (calc_volume_flow, [1, -1], "density_kg_m3"),
        (calc_split_flow, [-1, 0.3], "total_flow_kg_h"),
        (calc_split_flow, [1, -0.01], "split_fraction"),
        (calc_split_flow, [1, 1.01], "split_fraction"),
        (calc_residence_time, [0, 1], "vessel_volume_m3"),
        (calc_residence_time, [-1, 1], "vessel_volume_m3"),
        (calc_residence_time, [1, 0], "volume_flow_m3_h"),
        (calc_residence_time, [1, -1], "volume_flow_m3_h"),
        (calc_heating_energy, [1, -1], "duration_h"),
    ],
)
def test_physical_ranges(function, arguments, message):
    with pytest.raises(ValueError, match=message):
        function(*arguments)


@pytest.mark.parametrize(
    ("function", "arguments", "message"),
    [
        (calc_volume_flow, [1e308, 1e-308], "volume_flow_m3_h"),
        (calc_residence_time, [1e308, 1e-308], "residence_time_h"),
        (calc_residence_time, [1e307, 1], "residence_time_min"),
        (calc_heating_energy, [1e308, 2], "energy_kwh"),
        (calc_heating_energy, [1e306, 1], "energy_kj"),
        (calc_heating_energy, [-1e306, 1], "energy_kj"),
    ],
)
def test_result_overflow_is_rejected(function, arguments, message):
    with pytest.raises(ValueError, match=message):
        function(*arguments)


def test_split_large_flow_stays_finite_and_conserved():
    result = calc_split_flow(1e308, 0.5)
    assert result["branch_flow_kg_h"] == 5e307
    assert result["remainder_flow_kg_h"] == 5e307
