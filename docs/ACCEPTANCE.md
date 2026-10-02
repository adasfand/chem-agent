# 功能与验证对应

版本 `0.2.0`，核对日期 2026-10-02。本表按当前源码和运行记录组织；历史开发骨架 `483e780` 的待验证清单由本表替代。

## 当前证据

- 157 项 Python 离线测试、12 项前端状态测试、Ruff 检查通过。
- 新工作台完成 3 轮真实 DeepSeek 任务，9 次模型请求成功：缺参、补参、独立热负荷。
- 全新目录和独立虚拟环境完成锁定安装、无密钥检查、15 卡索引、157 项测试及 API/静态资源检查。
- 汇总：[本版检查记录](validation/v0.2.0/checks.json)；过程说明：[技术与验证报告](技术与验证报告.md)。

## 功能 → 实现 → 证据

| 功能 | 当前实现 | 实际证据与检查范围 |
| --- | --- | --- |
| 资料组织、分段和索引 | [knowledge.py](../src/chem_agent/knowledge.py)、[15 张知识卡](../data/knowledge/)；`chem-agent index` 重建索引并输出清单 | [检索回归](../tests/test_knowledge.py)覆盖来源、资料更新、同义表达和无关查询；独立复装确认 15 卡索引成功 |
| 检索增强与引用 | `search_knowledge` 返回正文和 `chunk_id`；工具观察回传模型，回答引用限于本轮命中片段 | [本轮热负荷记录](validation/v0.2.0/20261002T090531-abe3bc609c.json)保存实际检索、请求观察和引用；独立知识问答案例见[历史 8 例清单](validation/live_validation.json) |
| 计划与真实执行 | [agent.py](../src/chem_agent/agent.py)、[execution.py](../src/chem_agent/execution.py)；先登记计划，再按依赖执行注册工具 | [执行器回归](../tests/test_execution.py)及[Agent 回归](../tests/test_agent.py)；本轮真实记录含计划、实际参数、结果和状态 |
| 多工具结果引用 | `{"$ref":"s2.value"}` 由程序读取成功步骤返回值，检查依赖和单位后注入计算 | [本轮热负荷记录](validation/v0.2.0/20261002T090531-abe3bc609c.json)显示换算值 `0.277777… kg/s` 被计算消费，结果 `46.444444… kW`；[引用边界回归](../tests/test_execution_review.py) |
| 单位、显热和混合计算 | [calculations.py](../src/chem_agent/calculations.py)中的固定函数；单位、范围、温度/温差分别检查 | [数值回归](../tests/test_calculations.py)覆盖参考计算与非法输入；本轮实际验证显热，混合/换算等真实案例保留在历史清单 |
| 缺参及补充 | `needs_input` 后生成新运行，工作台保存 `parent_run_id`，带最近上下文重新规划 | [缺参记录](validation/v0.2.0/20261002T085857-8f6a1e4df1.json)未执行热负荷；[补参记录](validation/v0.2.0/20261002T085908-f380cc8622.json)关联前轮并得到 `46.444444… kW` |
| 失败、取消和隔离 | [ui.py](../src/chem_agent/ui.py)管理会话与单模型任务；请求返回及工具入口检查取消，保留已完成步骤 | [API 测试](../tests/test_ui_api.py)、[取消测试](../tests/test_cancellation.py)、[前端状态测试](../tests/frontend_state.test.cjs)；失败和取消采用离线模拟验证 |
| 工作台与状态恢复 | [web/](../src/chem_agent/web/)；输入/结果并排，结论/过程/依据标签，Cookie 关联内存会话 | 实际浏览器验证标签、参数展开、资料浏览、刷新恢复；3 种布局尺寸经 DOM 检查无根页面溢出，见[检查记录](validation/v0.2.0/checks.json)与[工作台截图](validation/v0.2.0/workbench.png) |
| 报告与追溯导出 | [report.py](../src/chem_agent/report.py)生成 Markdown；终态可导出 JSON；数值取自成功工具输出 | 浏览器实际下载两种文件；[报告回归](../tests/test_report.py)及[本版示例报告](validation/v0.2.0/sample-report.md) |
| 可复现源码包 | [pyproject.toml](../pyproject.toml)、[uv.lock](../uv.lock)、[白名单打包](../scripts/package.py)；页面资源随源码及 wheel 分发 | 本机独立解压、独立环境 `uv sync --locked`、无凭据 `doctor`、索引、157 项测试及 API/资源检查均通过；wheel 含 HTML/CSS/JS |
| 使用与维护说明 | [README](../README.md)、[技术与验证报告](技术与验证报告.md)、[变更记录](../CHANGELOG.md) | 文档列出实际命令、状态、补参、导出、记录生命周期和版本迁移；证据文件均可定位 |

## 复验入口

```bash
uv sync --locked
uv run chem-agent doctor
uv run chem-agent index
uv run pytest
node --test tests/frontend_state.test.cjs  # 可选开发检查，运行系统不需 Node
```

`uv run python scripts/validate_live.py` 会重新发起 8 个模型案例并消耗 API 额度；本轮新增实测为上表所列 3 轮，未把历史 8 例计为本轮重跑。

## 验证边界

本版检查环境为 macOS、Python 3.12。Windows、完全离线模型、生产多人部署和未收录主题准确率尚未验证。程序检查工具参数、数值、状态及引用成员关系；最终说明的全部语义和工况一致性仍需核对。服务重启后界面会话重置，`runs/` 原始记录保留。
