"""Thin Gradio page; every submitted task gets a fresh Agent and private trace."""
import json
import os
from pathlib import Path

import gradio as gr

from chem_agent.config import Settings
from chem_agent.service import run_task
from chem_agent.trace import redact


def main():
    settings = Settings.load(Path(__file__).resolve().parent)
    examples = json.loads((settings.root / "examples/tasks.json").read_text(encoding="utf-8"))

    def submit(mode, question):
        try:
            result = run_task(settings, question, mode)
            text = result["answer"] if result["status"] == "completed" else f"本次未完成：{result['error']}"
            return text, result
        except Exception as exc:
            return redact(f"启动失败：{exc}", (settings.api_key, settings.api_base)), {"status": "failed"}

    with gr.Blocks(title="化工知识与工具助手") as demo:
        gr.Markdown("# 化工知识与工具助手\n查询知识依据，演示单位换算、显热和混合衡算。")
        mode = gr.Radio([("知识问答", "ask"), ("工具任务", "task")], value="task", label="任务类型")
        question = gr.Textbox(lines=5, label="输入问题与已知条件")
        gr.Examples([[c["mode"], c["question"]] for c in examples], inputs=[mode, question])
        button = gr.Button("执行")
        answer = gr.Markdown()
        record = gr.JSON(label="本次计划、参数结果与记录位置")
        button.click(submit, [mode, question], [answer, record], concurrency_limit=1)
    demo.queue().launch(server_name=os.getenv("CHEM_UI_HOST", "127.0.0.1"),
                        server_port=int(os.getenv("CHEM_UI_PORT", "7860")), share=False)


if __name__ == "__main__":
    main()
