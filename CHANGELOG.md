# Changelog

## 0.3.0 — 2026-10-02

- 接入 LightRAG 1.5.7 图谱与向量混合检索，并使用 FastEmbed 中文向量模型；显式 `rag-index` 构建持久索引，索引缺失或资料变动时明确显示词法回退。
- 新增 6 张有官方出处、章节和适用边界的中文资料卡；保留原有 15 张自编教学卡。
- 工作台新增本轮检索与工具执行路径，可核对实际实体关系、命中片段、来源、调用结果和数值引用；问题模板移出主视觉区。
- 继续使用 smolagents 工具调用框架及原有确定性计算、单位校验和 `$ref` 来源追溯。
- 实测 21 卡中文图谱、真实 `mix` 检索与浏览器三步工具样例；图谱非命中支撑片段也可追溯原文，索引缓存采用私有权限并校验完整性；174 项 Python、15 项前端离线测试通过，详见 [0.3.0 检查记录](docs/validation/v0.3.0/checks.json)。

## 0.2.0 — 2026-10-02

### 新增与调整

- 用 FastAPI/uvicorn 和原生 HTML/CSS/JavaScript 工作台替换 Gradio；输入与结果并排，长内容在面板内滚动，无需前端构建。
- 增加“结论 / 过程 / 依据”视图、工具数值卡、资料浏览、任务历史与刷新恢复。
- 增加 Markdown 文字报告和 JSON 追溯双导出；数值来自成功工具调用，模型说明单独展示。
- 通过 Cookie 隔离内存会话；单进程同时处理一个模型任务。补参生成带 `parent_run_id` 的新运行。
- 增加请求返回后和工具执行前的取消检查，保留取消前已完成步骤；处理重复提交、迟到响应、会话过期和保存失败。
- 提供锁定依赖、白名单源码包和包含静态资源的 wheel；补齐使用说明、技术报告及功能验证矩阵。

### 不兼容变更

| 旧开发骨架 | 当前版本 | 迁移方式 |
| --- | --- | --- |
| CLI `ask`、`task` | `uv run chem-agent run "问题"` | 问答与工具任务使用同一入口 |
| CLI `build-index` | `uv run chem-agent index` | 从知识卡重建索引，写入 `build/knowledge_manifest.json` |
| `runs/<run_id>/events.jsonl` 和 `result.json` | `runs/<run_id>.json` | 使用新记录格式；旧记录不自动导入当前会话 |
| `environment.yml` Conda 环境草案 | `uv sync --locked` | 按 `pyproject.toml` 与 `uv.lock` 安装；不用旧草案覆盖锁定环境 |
| `service.py`、`tests/test_tools.py`、`data/knowledge-example` 与待填报告模板 | 当前 `src/chem_agent/`、`tests/`、`data/knowledge/` 和技术报告 | 使用当前目录；旧文件保留在 Git 历史，不混入运行工程 |

原开发骨架的内部 API 与可配置项不保持兼容，以新版 README 为准。

### 验证

- 157 项 Python 离线测试、12 项前端状态测试及 Ruff 检查通过。
- 3 轮真实 DeepSeek 任务，9 次请求成功；验证缺参、补参关联和独立热负荷计算。
- 验证三种视口、标签/资料操作、Markdown/JSON 下载、刷新恢复。
- 独立解压和虚拟环境安装通过；检查索引、测试、API、静态资源和 wheel 内容。
- 详情：[检查记录](docs/validation/v0.2.0/checks.json)、[功能验证矩阵](docs/ACCEPTANCE.md)。

## 历史基线

远程父提交 `483e780`（“第一次提交测试”）为早期开发骨架，原 README 标注仅静态审查，动态验证未执行。`docs/IMPLEMENTATION_PLAN.md`、`docs/RESEARCH_REPORT_TEMPLATE.md`、`environment.yml` 及旧模块可在该提交中查阅。当前安装、命令和验证以 `0.3.0` README 为准。
