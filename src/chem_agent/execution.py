"""Thin domain guard around framework calls; no custom Agent execution loop."""
from copy import deepcopy
import re

from pydantic import BaseModel, ConfigDict, Field

from .tools import FUNCTIONS, SCHEMAS, ureg


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str = Field(pattern=r"^s[1-9][0-9]*$")
    goal: str = Field(min_length=1)
    tool_name: str
    depends_on: list[str] = Field(default_factory=list)
    input_refs: dict[str, str]


class ExecutionContext:
    def __init__(self, trace, index, settings, mode="task"):
        self.trace, self.index, self.settings, self.mode = trace, index, settings, mode
        self.plan: dict[str, PlanStep] = {}
        self.outputs: dict[str, dict] = {}
        self.status: dict[str, str] = {}
        self.citations: dict[str, dict] = {}
        self.plan_version = 0

    def record_plan(self, steps: list[dict]) -> dict:
        if not steps or len(steps) > self.settings.max_steps:
            raise ValueError("计划不能为空或超过步数上限")
        parsed = [PlanStep.model_validate(s) for s in steps]
        seen = set()
        for step in parsed:
            if step.step_id in seen or any(dep not in seen for dep in step.depends_on):
                raise ValueError("步骤ID重复、前向依赖或循环依赖；请按执行顺序提交")
            if step.tool_name not in SCHEMAS or (self.mode == "ask" and step.tool_name != "search_knowledge"):
                raise ValueError("此模式不允许该工具")
            for ref in step.input_refs.values():
                if ref.startswith("user:") and ref[5:].strip():
                    continue
                upstream, separator, field = ref.partition(".")
                if not separator or not field or upstream not in step.depends_on:
                    raise ValueError("input_refs 必须为 user:输入依据 或依赖步骤.返回字段")
            seen.add(step.step_id)
        new_plan = {s.step_id: s for s in parsed}
        for sid in self.outputs:
            if sid not in new_plan or new_plan[sid] != self.plan[sid]:
                raise ValueError("重新规划不得删除或改写已经成功执行的步骤")
        self.plan = new_plan
        self.status = {sid: self.status.get(sid, "pending") if sid in self.outputs else "pending"
                       for sid in self.plan}
        self.plan_version += 1
        self.trace.event("plan", version=self.plan_version, steps=[s.model_dump() for s in parsed])
        return {"plan_version": self.plan_version, "status": self.status}

    def execute(self, tool_name: str, step_id: str, arguments: dict) -> dict:
        resolved = deepcopy(arguments)
        try:
            if step_id not in self.plan or self.plan[step_id].tool_name != tool_name:
                raise ValueError("先调用 record_plan；step_id 与计划工具必须一致")
            step = self.plan[step_id]
            if step_id in self.outputs:
                raise ValueError("成功步骤不能重复执行；新计算请增加新步骤")
            if any(self.status.get(dep) != "success" for dep in step.depends_on):
                raise ValueError("依赖步骤尚未成功，拒绝执行")
            if set(arguments) - set(step.input_refs):
                raise ValueError("每个显式参数都必须有计划 input_refs")
            for key, ref in step.input_refs.items():
                if ref.startswith("user:"):
                    if key not in arguments:
                        raise ValueError(f"缺少用户输入参数：{key}")
                    continue
                upstream, _, path = ref.partition(".")
                value = self.outputs[upstream]
                for part in path.split("."):
                    value = value[int(part)] if isinstance(value, list) else value[part]
                # Canonical value comes from successful execution, never model copy.
                resolved[key] = deepcopy(value)
                if tool_name == "calc_heat_duty":
                    expected = {"mass_flow_kg_s": "kg/s", "cp_kj_kg_k": "kJ/(kg*K)", "delta_t_k": "K"}
                    if key in expected:
                        output = self.outputs[upstream]
                        if self.plan[upstream].tool_name != "convert_units" or path != "value":
                            raise ValueError("热负荷数值引用必须来自 convert_units.value，以核对单位")
                        scale = ureg.Quantity(1, output["unit"]).to(expected[key]).magnitude
                        if abs(scale - 1) > 1e-12:
                            raise ValueError(f"引用数值单位必须与 {expected[key]} 一致，请先重新换算")
                        if key == "delta_t_k" and output["quantity_kind"] != "temperature_difference":
                            raise ValueError("热负荷必须引用温差，不能引用绝对温度")
            if tool_name == "search_knowledge":
                resolved.setdefault("top_k", self.settings.top_k)
            data = SCHEMAS[tool_name].model_validate(resolved)
            self.status[step_id] = "running"
            self.trace.event("tool_start", step_id=step_id, tool_name=tool_name,
                             plan_version=self.plan_version, depends_on=step.depends_on,
                             input_refs=step.input_refs, supplied_arguments=arguments, arguments=data.model_dump())
            if tool_name == "search_knowledge":
                result = self.index.search(data.query, data.top_k, self.settings.min_score)
                self.citations.update({hit["chunk_id"]: hit for hit in result["hits"]})
            else:
                result = FUNCTIONS[tool_name](data)
            self.outputs[step_id] = result
            self.status[step_id] = "success"
            self.trace.event("tool_result", step_id=step_id, tool_name=tool_name, status="success", output=result)
            return {"step_id": step_id, "status": "success", "output": result}
        except Exception as exc:
            if step_id in self.plan and step_id not in self.outputs:
                self.status[step_id] = "failed"
            self.trace.event("tool_result", step_id=step_id, tool_name=tool_name, status="failed",
                             supplied_arguments=arguments, arguments=resolved, error=str(exc))
            raise

    def validate_answer(self, answer, memory=None, **kwargs) -> bool:
        text = str(answer)
        if not text.strip():
            raise ValueError("最终回答不能为空")
        if not self.plan or any(self.status.get(sid) != "success" for sid in self.plan):
            raise ValueError("存在未完成计划；修正或重新规划后回答")
        references = set(re.findall(r"\[来源:([^\]]+)\]", text))
        if references - self.citations.keys():
            raise ValueError("引用包含本次未检索到的片段")
        if self.citations and not references:
            raise ValueError("回答需要使用 [来源:chunk_id] 引用实际检索片段")
        if self.mode == "ask" and not any(s.tool_name == "search_knowledge" for s in self.plan.values()):
            raise ValueError("知识问答必须实际检索")
        return True
