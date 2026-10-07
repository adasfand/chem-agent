"""Validated execution and explicit references to earlier results."""

from __future__ import annotations

import inspect
import re
from copy import deepcopy
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from chem_agent.answers import calculation_answer, calculation_explanation
from chem_agent.calculations import calc_heat_duty, calc_mass_balance, convert_units
from chem_agent.knowledge import KnowledgeBase
from chem_agent.trace import RunTrace, utc_now

TOOL_NAMES = {"search_knowledge", "convert_units", "calc_heat_duty", "calc_mass_balance"}


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    step_id: str = Field(pattern=r"^s[1-9][0-9]?$", max_length=3)
    goal: str = Field(min_length=1, max_length=200)
    tool_name: Literal["search_knowledge", "convert_units", "calc_heat_duty", "calc_mass_balance"]
    depends_on: list[str] = Field(default_factory=list, max_length=6)


class Execution:
    def __init__(self, knowledge: KnowledgeBase, trace: RunTrace):
        self.knowledge = knowledge
        self.trace = trace
        self.results: dict[str, dict] = {}
        self.functions = {
            "search_knowledge": knowledge.search,
            "convert_units": convert_units,
            "calc_heat_duty": calc_heat_duty,
            "calc_mass_balance": calc_mass_balance,
        }

    def set_plan(self, steps: list[dict]) -> dict:
        if self.trace.data["status"] != "running":
            raise ValueError("任务已经结束。")
        if self.trace.data["plan"]:
            raise ValueError("本次任务已建立计划；请按现有步骤执行或说明阻塞原因。")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 6:
            raise ValueError("计划需要包含 1–6 个步骤。")
        parsed = [PlanStep.model_validate(step) for step in steps]
        seen = set()
        for step in parsed:
            if step.step_id in seen or not set(step.depends_on) <= seen:
                raise ValueError("步骤编号不能重复；依赖只能指向计划中更早的步骤。")
            seen.add(step.step_id)
        self.trace.data["plan"] = [dict(step.model_dump(), status="pending") for step in parsed]
        self.trace.save()
        return {"status": "accepted", "steps": self.trace.data["plan"]}

    def _resolve(
        self, value: Any, dependencies: list[str], refs: list[dict], path="", units=None
    ) -> Any:
        if isinstance(value, dict):
            if "$ref" in value:
                if set(value) != {"$ref"} or not isinstance(value["$ref"], str):
                    raise ValueError("结果引用只能包含字符串 $ref。")
                ref = value["$ref"]
                parts = ref.split(".")
                if len(parts) < 2 or not re.fullmatch(r"s[1-9][0-9]?", parts[0]):
                    raise ValueError("结果引用格式应为 s2.value。")
                if parts[0] not in dependencies or parts[0] not in self.results:
                    raise ValueError("只能引用已成功执行且声明为依赖的步骤。")
                resolved: Any = self.results[parts[0]]
                for part in parts[1:]:
                    if not isinstance(resolved, dict) or part not in resolved:
                        raise ValueError("结果引用字段不存在。")
                    resolved = resolved[part]
                source = self.results[parts[0]]
                expected_unit = {
                    "mass_flow_kg_s": "kg/s",
                    "delta_t_k": "delta_K",
                }.get(path)
                if re.fullmatch(r"streams\[\d+\]\.flow_kg_h", path):
                    expected_unit = "kg/h"
                if units and path in units:
                    expected_unit = units[path]
                source_unit = (
                    source.get("unit")
                    if parts[-1] == "value"
                    else {
                        "total_flow_kg_h": "kg/h",
                        "component_flow_kg_h": "kg/h",
                        "mass_flow_kg_s": "kg/s",
                        "delta_t_k": "delta_K",
                    }.get(parts[-1])
                )
                record = {"argument": path, "ref": ref, "value": deepcopy(resolved)}
                if expected_unit:
                    if not source_unit:
                        raise ValueError("数值结果引用缺少可核对的单位。")
                    converted = convert_units(resolved, source_unit, expected_unit)["value"]
                    record.update(
                        source_value=resolved,
                        source_unit=source_unit,
                        unit=expected_unit,
                        value=converted,
                    )
                    resolved = converted
                if path == "specific_heat_kj_kg_k":
                    raise ValueError("当前工具不能提供比热，请使用用户明确给出的比热。")
                if (
                    re.fullmatch(r"streams\[\d+\]\.mass_fraction", path)
                    and parts[-1] != "mass_fraction"
                ):
                    raise ValueError("质量分数只能引用明确的 mass_fraction 字段。")
                refs.append(record)
                return deepcopy(resolved)
            return {
                k: self._resolve(v, dependencies, refs, f"{path}.{k}".strip("."), units)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [
                self._resolve(v, dependencies, refs, f"{path}[{i}]", units)
                for i, v in enumerate(value)
            ]
        return value

    def execute(self, tool_name: str, step_id: str, arguments: dict) -> dict:
        if self.trace.data["status"] != "running":
            raise ValueError("任务已经结束，不能继续调用工具。")
        started = perf_counter()
        call = {
            "call_id": f"call_{len(self.trace.data['calls']) + 1}",
            "step_id": step_id,
            "tool_name": tool_name,
            "requested_arguments": deepcopy(arguments),
            "arguments": None,
            "input_refs": [],
            "started_at": utc_now(),
            "status": "running",
        }
        self.trace.data["calls"].append(call)
        step = next((s for s in self.trace.data["plan"] if s["step_id"] == step_id), None)
        try:
            if len(self.trace.data["calls"]) > 12:
                raise ValueError("已达到本次任务的工具调用次数上限。")
            if not step or step["tool_name"] != tool_name:
                raise ValueError("工具和步骤必须与已登记计划一致。")
            retry_empty_search = (
                tool_name == "search_knowledge"
                and step_id in self.results
                and not self.results[step_id]["hits"]
            )
            if step["status"] == "succeeded" and not retry_empty_search:
                raise ValueError("此步骤已完成，请使用其现有结果。")
            if not all(dep in self.results for dep in step["depends_on"]):
                raise ValueError("前序步骤未成功，不能执行依赖计算。")
            if any(
                "hits" in self.results[dep] and not self.results[dep]["hits"]
                for dep in step["depends_on"]
            ):
                raise ValueError("前序检索没有证据，不能执行依赖步骤；请先重试该检索。")
            if not isinstance(arguments, dict):
                raise ValueError("arguments 必须是参数对象。")
            units = {"value": arguments.get("from_unit")} if tool_name == "convert_units" else None
            resolved = self._resolve(arguments, step["depends_on"], call["input_refs"], units=units)
            call["arguments"] = resolved
            # A flow conversion dependency requires a real, unit-checked flow
            # reference; a later mass balance may provide the flow being heated.
            conversion_deps = []
            for prior in self.trace.data["plan"]:
                if prior["step_id"] in step["depends_on"] and prior["tool_name"] == "convert_units":
                    try:
                        convert_units(1, self.results[prior["step_id"]]["unit"], "kg/s")
                    except ValueError:
                        continue
                    conversion_deps.append(prior["step_id"])
            if tool_name == "calc_heat_duty" and conversion_deps:
                if not any(
                    r["argument"] == "mass_flow_kg_s" and r.get("unit") == "kg/s"
                    for r in call["input_refs"]
                ):
                    raise ValueError(
                        "质量流量必须用 $ref 引用已成功依赖步骤的流量结果，不能重抄数值。"
                    )
            try:
                inspect.signature(self.functions[tool_name]).bind(**resolved)
            except TypeError:
                raise ValueError("工具参数缺失或存在多余字段，请按工具说明提供参数。") from None
            step["status"] = "running"
            self.trace.save()
            output = self.functions[tool_name](**resolved)
            self.results[step_id] = output
            call.update(output=output, status="succeeded")
            step["status"] = "succeeded"
            if tool_name == "search_knowledge":
                existing = {h["chunk_id"] for h in self.trace.data["evidence"]}
                self.trace.data["evidence"].extend(
                    h for h in output["hits"] if h["chunk_id"] not in existing
                )
            return {"step_id": step_id, "status": "succeeded", "output": output}
        except (ValueError, TypeError, KeyError) as exc:
            if step and step["status"] != "succeeded":
                step["status"] = "failed"
            call.update(status="failed", error=str(exc))
            raise ValueError(str(exc)) from None
        finally:
            call["finished_at"] = utc_now()
            call["latency_ms"] = round((perf_counter() - started) * 1000, 3)
            self.trace.save()

    def complete(
        self, answer: str, status: str, citations: list[str], explanation: str | None = ""
    ) -> str:
        if self.trace.data["status"] != "running":
            raise ValueError("任务已经结束，不能改写最终状态或回答。")
        if status not in {"completed", "needs_input", "no_evidence", "failed", "out_of_scope"}:
            raise ValueError("未知任务状态。")
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 16000:
            raise ValueError("回答必须是非空的简短文本。")
        if explanation is None:
            explanation = ""
        if not isinstance(explanation, str) or len(explanation) > 6000:
            raise ValueError("补充说明需要是最多 6000 字的文本。")
        evidence_ids = {h["chunk_id"] for h in self.trace.data["evidence"]}
        if not isinstance(citations, list) or any(not isinstance(c, str) for c in citations):
            raise ValueError("citations 必须是来源编号列表。")
        if not set(citations) <= evidence_ids:
            raise ValueError("引用必须来自本次实际检索命中的 chunk_id。")
        if status == "completed":
            if not self.trace.data["plan"] or any(
                s["status"] != "succeeded" for s in self.trace.data["plan"]
            ):
                raise ValueError("计划尚未全部成功执行，不能声明完成。")
            searches = [o for s, o in self.results.items() if "hits" in o]
            if any(not output["hits"] for output in searches):
                raise ValueError("计划中的检索没有证据，请重试该检索或使用 no_evidence 状态。")
            if evidence_ids and not citations:
                raise ValueError("回答需要引用本次检索来源。")
            verified_answer = calculation_answer(self.trace.data["calls"])
            if verified_answer is not None:
                extra = calculation_explanation(
                    explanation, self.trace.data["calls"], self.trace.data["evidence"], citations
                )
                self.trace.data["model_answer"] = answer
                self.trace.data["answer_source"] = (
                    "verified_tools_with_explanation" if extra else "verified_tools"
                )
                if explanation.strip():
                    self.trace.data["model_explanation"] = explanation
                answer = verified_answer + extra
        self.trace.finish(status, answer, citations)
        return answer
