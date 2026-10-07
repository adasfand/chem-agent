"""Narrow matching of explicitly supplied mass heat capacity in trusted user text."""

from __future__ import annotations

import math
import re
import unicodedata

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?"
_CAPACITY = re.compile(
    rf"(?<![\da-z.])(?P<value>{_NUMBER})\s*(?P<energy>kj|j|千焦|焦耳)\s*/\s*(?P<open>\()?\s*"
    r"(?:kg|千克|公斤)\s*[·⋅*×/\s]+\s*(?:kelvin|k|°c|摄氏度|开尔文)(?![a-z])\s*(?(open)\))(?![a-z0-9/·⋅*×])",
    re.IGNORECASE,
)


def supplied_specific_heat(value: float, user_inputs: list[str]) -> dict:
    """Match the latest supplied capacity, never retrieval or assistant text.

    Supported expressions carry J or kJ per kg per K (or Celsius interval).
    This does not prove arbitrary natural-language parameter attribution.
    Unrecognized or ambiguous expressions require clarification.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("比热需要是有限数值。")
    for index in range(len(user_inputs) - 1, -1, -1):
        text = unicodedata.normalize("NFKC", user_inputs[index]).casefold()
        candidates = []
        for match in _CAPACITY.finditer(text):
            prefix = re.split(r"[。；\n]", text[: match.start()])[-1]
            if not re.search(r"比热|(?:^|[^a-z])c_?p(?:[^a-z]|$)", prefix):
                continue
            if re.search(r"不要使用|不使用|不采用|不能使用|不是|不得|仅.*(?:算例|示例)", prefix):
                continue
            number = float(match["value"])
            if match["energy"] in {"j", "焦耳"}:
                number /= 1000
            if math.isfinite(number) and number > 0:
                candidates.append(number)
        if candidates:
            if len(set(candidates)) != 1:
                break
            if math.isclose(value, candidates[0], rel_tol=1e-9, abs_tol=1e-12):
                return {
                    "argument": "specific_heat_kj_kg_k",
                    "source": "user",
                    "user_message_index": index,
                    "value": candidates[0],
                    "unit": "kJ/(kg·K)",
                }
            break
        if re.search(
            rf"(?:比热(?:容)?|c_?p)\s*(?:改为|为|是|等于|=|:|：)?\s*{_NUMBER}"
            r"|(?:比热(?:容)?|c_?p)[^。；\n]{0,16}(?:未知|未给|未提供|不确定|缺少)"
            r"|(?:缺少|没有|未给出|未提供)[^。；\n]{0,4}(?:比热|c_?p)",
            text,
        ):
            # A changed value with missing/unsupported units, or an explicit
            # withdrawal, cannot silently revive an older supplied capacity.
            break
    raise ValueError(
        "比热未匹配当前问题或用户历史中明确给出的质量比热数值及单位；"
        "不能使用教学算例或助手答复中的物性。请以 needs_input 请求补充比热及单位，"
        "不要默认 4.18 或其他物性。支持 J/(kg·K) 或 kJ/(kg·K)。"
    )
