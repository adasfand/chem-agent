"""Heat capacity comes from explicit user quantities, never teaching examples."""

import pytest

from chem_agent.inputs import supplied_specific_heat


@pytest.mark.parametrize(
    "text",
    [
        "比热4.18 kJ/(kg·K)",
        "cp = 4180 J/(kg K)",
        "质量比热为4.18 千焦/(千克·开尔文)",
        "比热４．１８ ｋＪ／（ｋｇ・Ｋ）".replace("・", "·"),
        "比热4.18e3 J/kg/°C",
    ],
)
def test_capacity_normalizes_user_units(text):
    source = supplied_specific_heat(4.18, [text])
    assert source["source"] == "user"
    assert source["user_message_index"] == 0
    assert source["value"] == pytest.approx(4.18)


@pytest.mark.parametrize(
    "texts",
    [
        ["某液体1000 kg/h，从25℃加热到65℃，请计算热负荷。"],
        ["4.18℃，比热未知。"],
        ["不要使用4.18 kJ/(kg·K)，比热尚未给定。"],
        ["比热4.18 kJ/(kg·K)", "比热改为2.5 kJ/(kg·K)"],
        ["比热4.18 kJ/(kg·K)", "比热改为2.5"],
        ["比热4.18 kJ/(kg·K)", "比热未知"],
        ["比热4.18 kJ/(kg·K)", "比热不要使用4.18 kJ/(kg·K)，该值已撤回。"],
        ["比热未知，教材示例4.18 kJ/(kg·K)。"],
        ["比热4.18 kJ/(kg·kPa)"],
        ["比热4.18 kJ/(kg·kg)"],
        ["比热4.18 kJ/(kg·K/mol)"],
        [
            "比热4.18 kJ/(kg·K)",
            "不要使用比热4.18 kJ/(kg·K)，该值已撤回。",
        ],
        ["两液体比热分别4.18 kJ/(kg·K)、2.5 kJ/(kg·K)。"],
    ],
)
def test_missing_wrong_or_ambiguous_capacity_requires_input(texts):
    with pytest.raises(ValueError, match="needs_input"):
        supplied_specific_heat(4.18, texts)


def test_latest_explicit_capacity_supersedes_prior_value():
    texts = ["比热4.18 kJ/(kg·K)", "比热改为2.5 kJ/(kg·K)", "流量改为2000kg/h，继续计算。"]
    assert supplied_specific_heat(2.5, texts)["user_message_index"] == 1


def test_unchanged_capacity_can_still_use_user_history():
    texts = ["比热4.18 kJ/(kg·K)", "流量改为2000kg/h，比热不变。"]
    assert supplied_specific_heat(4.18, texts)["user_message_index"] == 0
