"""CLI and UI share one isolated run service."""
import json
from .agent import build_agent
from .execution import ExecutionContext
from .knowledge import KnowledgeIndex
from .trace import RunTrace


def run_task(settings, question: str, mode: str = "task") -> dict:
    if mode not in {"ask", "task"} or not question.strip():
        raise ValueError("请选择 ask/task 并输入非空问题")
    settings.require_model()
    index = KnowledgeIndex.load(settings.index_dir, settings.knowledge_dir)
    trace = RunTrace(settings.runs_dir, (settings.api_key, settings.api_base))
    trace.event("run_start", question=question, mode=mode, config=settings.public_summary(),
                corpus_sha256=index.snapshot["corpus_sha256"])
    context = ExecutionContext(trace, index, settings, mode)
    answer, state, error = "", "failed", None
    try:
        agent = build_agent(settings, context)
        result = agent.run(question, return_full_result=True)
        answer = str(result.output)
        trace.event("framework_end", state=result.state)
        if result.state != "success":
            raise RuntimeError(f"Agent 未正常结束：{result.state}")
        # Recheck here: framework max-step fallbacks can bypass final_answer_checks.
        context.validate_answer(answer)
        state = "completed"
    except Exception as exc:
        error = str(exc)
        trace.event("run_error", error=error)
    summary = {"status": state, "answer": answer, "error": error,
               "plan": [s.model_dump() for s in context.plan.values()],
               "step_status": context.status, "outputs": context.outputs,
               "citations": list(context.citations.values()),
               "acceptance_status": "not_evaluated"}
    trace.finish(**summary)
    return json.loads(trace.encode({"run_id": trace.run_id,
                                    "record_path": str(trace.directory / "result.json"), **summary}))
