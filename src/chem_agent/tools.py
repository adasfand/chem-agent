"""Narrow smolagents tools backed by the validated local execution layer."""

import threading

from smolagents import Tool

from chem_agent.engineering_tools import EXTRA_TOOL_DESCRIPTIONS
from chem_agent.execution import Execution
from chem_agent.model import RunCancelled

DESCRIPTIONS = {
    "search_knowledge": '检索本地化工资料；索引就绪时使用 LightRAG 图谱与向量混合检索。arguments={"query":"显热公式适用条件","top_k":3}。返回 hits 的 chunk_id 用于引用；retrieval 包含本轮实际实体、关系和片段。无命中时可用新查询重试同一步；依赖它的步骤被阻断，不能声明整轮完成。命中不代表事实正确，无相关资料时不能编造来源。',
    "convert_units": '换算兼容量纲的常用单位。arguments={"value":1000,"from_unit":"kg/h","to_unit":"kg/s"}。返回 value、unit。温差用 delta_degC、delta_K；绝对温度用 degC、K。',
    "calc_heat_duty": '计算单相恒比热显热负荷。arguments={"mass_flow_kg_s":{"$ref":"s2.value"},"specific_heat_kj_kg_k":4.18,"delta_t_k":40}。比热必须由用户给出，不能查表代填。温差可由明确起止温度作差。若依赖换算步骤，质量流量必须使用 $ref。返回 heat_duty_kw、inputs、assumptions。',
    "calc_mass_balance": '稳态无反应混合衡算。arguments={"streams":[{"flow_kg_h":100,"mass_fraction":0.05},{"flow_kg_h":400,"mass_fraction":0}]}。质量分数必须在0..1，百分数5%写0.05；纯水中盐分数为0。禁止将摩尔分数当质量分数。返回 total_flow_kg_h、component_flow_kg_h、mass_fraction，不返回 value。后续引用混合总流量使用 {"$ref":"s2.total_flow_kg_h"}（s2为实际混合步骤编号）。',
}
DESCRIPTIONS.update(EXTRA_TOOL_DESCRIPTIONS)


def check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event and cancel_event.is_set():
        raise RunCancelled("任务已取消。")


class BusinessTool(Tool):
    output_type = "object"
    inputs = {
        "step_id": {"type": "string", "description": "已登记计划中的步骤编号，例如 s1。"},
        "arguments": {
            "type": "object",
            "description": '工具参数；前序输出引用写成 {"$ref":"s2.value"}。',
        },
    }

    def __init__(
        self, name: str, execution: Execution, cancel_event: threading.Event | None = None
    ):
        self.name = name
        self.description = DESCRIPTIONS[name]
        self.execution = execution
        self.cancel_event = cancel_event
        super().__init__()

    def forward(self, step_id: str, arguments: dict) -> dict:
        check_cancelled(self.cancel_event)
        return self.execution.execute(self.name, step_id, arguments)


class PlanTool(Tool):
    name = "set_plan"
    description = "登记1至10步业务计划，必须在业务工具之前调用，可作为多工具批次的唯一首项。steps 中每项包含 step_id(s1等)、goal、tool_name、depends_on(前序编号数组)。仅可选注册的9种业务工具（知识检索、单位、显热、混合、温差、体积流量、分流、停留时间、传热量）。显热与混合计算必须直接或经前序依赖连接到已登记的检索步骤；例如s1检索、s2混合(depends_on=['s1'])、s3换算(depends_on=['s2'])、s4显热(depends_on=['s3'])。现有前序检索的必需依赖漏写时，执行器补全并返回dependency_adjustments。参数不足时不要计划计算，直接请求补充。"
    inputs = {"steps": {"type": "array", "description": "1–10个依赖顺序排列的步骤对象。"}}
    output_type = "object"

    def __init__(self, execution: Execution, cancel_event: threading.Event | None = None):
        self.execution = execution
        self.cancel_event = cancel_event
        super().__init__()

    def forward(self, steps: list[dict]) -> dict:
        check_cancelled(self.cancel_event)
        return self.execution.set_plan(steps, normalize_retrieval_dependencies=True)


class FinalTool(Tool):
    name = "final_answer"
    description = "提交用户可见的中文回答。完成计算必须写数值、单位和适用条件；缺参时提问，不能猜值。citations 只能取本次检索 hits 的 chunk_id。"
    inputs = {
        "answer": {
            "type": "string",
            "description": "简洁中文回答，不包含内部思考；使用工具真实结果。",
        },
        "status": {
            "type": "string",
            "description": "completed/needs_input/no_evidence/failed/out_of_scope 五者之一。",
        },
        "citations": {"type": "array", "description": "真实 chunk_id 字符串列表；未检索时为空。"},
        "explanation": {
            "type": "string",
            "nullable": True,
            "description": "用户要求概念解释时填写；否则为空。默认只写不含阿拉伯数字的概念文字和符号，不写数值例题、偏移常数或计算结果。计算数值由程序生成。若此字段校验失败，修改本字段而非answer。确需包含数字时，仅逐字复制本轮已引用原文的完整原句。",
        },
    }
    output_type = "string"

    def __init__(self, execution: Execution, cancel_event: threading.Event | None = None):
        self.execution = execution
        self.cancel_event = cancel_event
        if getattr(execution, "requires_explanation", False):
            self.description += (
                " 本轮用户明确要求概念解释：完成计算还必须提交非空 explanation，"
                "并先执行计划内检索、提供真实 citations。只在 answer 中解释不能完成。"
            )
        super().__init__()

    def forward(
        self, answer: str, status: str, citations: list[str], explanation: str | None = ""
    ) -> str:
        check_cancelled(self.cancel_event)
        return self.execution.complete(answer, status, citations, explanation)


def make_tools(execution: Execution, cancel_event: threading.Event | None = None) -> list[Tool]:
    return [
        PlanTool(execution, cancel_event),
        *[BusinessTool(name, execution, cancel_event) for name in DESCRIPTIONS],
        FinalTool(execution, cancel_event),
    ]
