# 交付范围与合同摘要符合性

版本：0.3.2；日期：2026-10-07。

本轮按仓库保留的七项合同摘要提供工程交付物。七项要求已整理于随包的 [交付范围依据](CONTRACT_SCOPE.md)，其仓库来源称引自《合同-单章.pdf》第 10–11 页。本轮没有重新取得原件，以下是工程能力映射与复验方法，不是扫描合同逐页或法律核验结论。

| 摘要要求 | 实际能力/文件 | 演示与验收方法 | 状态 |
|---|---|---|---|
| 1. 知识资源组织与构建 | `knowledge.py`、`retrieval.py`、21 卡 | doctor 看资料数量；index/search 核对分段、来源；rag-index 构建真实索引；来源/损坏/隔离回归 | 已实现，MD/TXT 范围 |
| 2. 检索与知识增强 | `search_knowledge`、`model.py`、实际请求观察 | 问答查看 hits 与 chunk_id，JSON 核对原文进入模型请求；检索未命中不得声明完成 | 已实现，覆盖收录主题 |
| 3. 知识增强处理流程 | `agent.py`、CLI/工作台、trace | 输入→登记计划→检索→答案→引用→导出在同一 run_id 可查 | 已实现 |
| 4. 任务解析与执行规划 | smolagents、`PlanStep`、`Execution` | 更改问题核对计划；依赖/非法批次/终态测试；max_steps 限制 | 已实现，有限步骤 |
| 5. 多工具选择与调用 | 四个业务工具、`calculations.py`、`$ref` | 显热流程检索→换算→计算；1000/2000 kg/h 对应约46.44/92.89 kW；核对 input_refs | 已实现；自由文本输入需人工核对 |
| 6. 源码、配置、依赖、说明和示例交付 | pyproject/uv.lock/.env.example、启动脚本、Docker、ZIP | 解压到新目录，uv sync --locked，离线 demo、测试、启动HTTP；接收方配置自己的密钥 | 已实现；平台验证见 checks |
| 7. 研究报告与实物一致 | 本页、ARCHITECTURE、AUDIT_AND_PLAN、技术与验证报告、版本 checks | 每项链接到源码和可复验入口；真实调用、离线模拟与历史记录分开 | 已提供 |

七项均有实现或交付文件，不把边界之外的能力计入完成数量。没有宣称实现模型训练、工业物性数据库、多 Agent 协作、复杂流程模拟或生产多用户平台。

## 最短离线验收

```bash
uv sync --locked
uv run chem-agent doctor
uv run chem-agent index
uv run chem-agent search "显热热负荷公式"
uv run python scripts/demo_offline.py
uv run python scripts/demo_offline.py --flow 2000
uv run pytest
node --test tests/frontend_state.test.cjs
```

demo_offline 执行真实本地检索和计算，不用密钥，不用 LightRAG，不证明模型会自行规划。Node 只用于可选开发检查，启动系统无需 Node。run_id、引用、数值依赖及结果保存在本机忽略目录 runs。

## 主流程与交付验收

配置接收方自己的密钥后启动 `uv run chem-agent ui`。输入 examples/tasks.json 中的知识问题、热负荷、混合衡算、单位换算、缺参/补参和错误单位案例；结果、计划、调用、来源及导出均可见。图谱需先 `uv run chem-agent rag-index`，该命令下载模型并消耗 API 额度。完整真实模型验收为 `uv run python scripts/validate_live.py`；历史案例不会自动变成本次通过结果。

容器入口：`docker compose up --build -d`；health：`curl http://127.0.0.1:7860/health`；具体 API 请求、Cookie/Origin 与配置方法见 README。构建 ZIP：`uv run python scripts/package.py`，同时生成 SHA256。

## 当前证据与剩余边界

本轮结果见 `validation/v0.3.2/checks.json`；0.3.0 真图谱和工作台历史证据仍见 `validation/v0.3.0/checks.json`，0.2.0 与更早记录按其版本保留，不冒充重跑。当前已确认的运行缺陷及修复回归在 AUDIT_AND_PLAN 中列明。

完成状态校验计划、检索业务结果和引用成员关系，不自动证明每个自然语言结论及用户参数归因正确。已完成的数值答复由成功工具结果与全部适用条件生成，原模型答复保留作审计；继续核对自由文本输入归因与实际工况是否符合假设。Windows、生产多人部署、全主题检索准确率和真实工业物性数据库未验证。会话历史在服务重启后不恢复；原始记录含业务数据，分发前应检查。
