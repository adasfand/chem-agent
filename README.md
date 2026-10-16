# 化工知识与计算助手

本项目提供化工专业知识检索、任务规划、确定性工具计算与结果追溯。知识资料库包含71份资料，工作台展示检索来源、实际工具参数、前序结果回用与回答引用。模型负责组织步骤，数值计算由本地函数完成。

## 统一综合演示

某连续配料系统中，两股含同一种溶质的水溶液进行混合：
- A液：1000 kg/h，溶质质量分数12%，温度25℃。
- B液：2000 kg/h，溶质质量分数3%，温度25℃。
混合液先从25℃加热到55℃，再加热到75℃，随后进入有效液体容积为1.5 m³的缓冲罐。
教学计算给定：混合液比热容恒为3.8 kJ/(kg·K)，缓冲罐工况下密度为1050 kg/m³。假设稳态、无反应、无相变，忽略混合热、热损失及动能和位能变化，无轴功。
请检索相关知识依据，完成：
1. 总质量衡算与溶质衡算，计算出口质量流量和质量分数。
2. 分别计算两级加热热负荷及总热负荷。
3. 将质量流量换算为缓冲罐工况下的体积流量，计算平均停留时间。
4. 解释质量分数与质量浓度、热量与热负荷、摄氏温度与开尔文温差的区别。
5. 说明恒比热公式的适用条件，以及发生相变或比热随温度明显变化时需要补充什么依据。
后续计算请复用前序工具结果，并给出知识来源、计算参数、单位和结果引用。

| 计算项目 | 结果 |
| --- | --- |
| 出口总质量流量 | 3000 kg/h |
| 溶质质量流量与质量分数 | 180 kg/h；6% |
| 第一级、第二级、总热负荷 | 95；63.333333…；158.333333… kW |
| 缓冲罐工况体积流量 | 2.857142857… m³/h |
| 平均停留时间 | 0.525 h = 31.5 min = 1890 s |
| 工况质量浓度 | 63 kg/m³ = 63 g/L |

工作台首页、默认离线演示及研究报告使用这道综合题。点击首页示例填入问题，发送后通过“演示本轮流程”查看知识网络、工具执行与回用、结果与引用。

## 安装与启动

运行环境：Python 3.11–3.13、uv、Node.js 22.12及以上兼容环境。首次安装依赖及调用远端模型使用网络。

```bash
uv sync --locked
cp .env.example .env
```

Windows PowerShell使用 `Copy-Item .env.example .env`。在本机 `.env` 设置 `DEEPSEEK_API_KEY`，也可通过 `DEEPSEEK_API_KEY_FILE` 指定只存放密钥的本机文件。模型名称及服务地址沿用 `.env.example` 中的配置项。

```bash
uv run chem-agent doctor
uv run chem-agent rag-index
uv run chem-agent ui
```

后端地址为 `http://127.0.0.1:7860`。另开终端启动Vue工作台：

```bash
cd src/chem_agent/web
npm ci
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。通过 `CHEM_PORT` 设置后端端口，前端通过 `CHEM_BACKEND_URL` 设置对应代理目标。`npm run build` 完成类型检查与生产构建。

`rag-index` 使用配置的模型提取知识实体和关系，并下载本地向量模型，产生相应API用量；索引保存在 `build/lightrag/`。`uv run chem-agent rag-status` 查看索引状态。资料更新后重新构建索引并重启服务。知识检索支持LightRAG图谱与向量混合模式以及本地词法模式，页面标注实际使用的检索方式。

## 离线综合演示

```bash
uv run python -m scripts.demo_offline
```

该命令执行固定的综合流程：检索、混合、三级温差、质量流量换算、两级及总热负荷、体积流量、停留时间。计算与结果引用均经过真实工具执行；模式标记为 `offline_demo`。JSON记录及Markdown报告写入 `runs/`。模型驱动的工作台运行标记为 `live`。

## 计算与追溯

九种业务工具包括知识检索、单位换算、混合衡算、显热负荷、温差、体积流量、两路分流、平均停留时间与恒定功率传热量。执行计划支持1至16步；模型可以一次提交多个工具动作，执行器按依赖顺序运行。

本题数据回用的主要路径为：混合总质量流量→kg/s换算→各段热负荷；混合总质量流量→工况体积流量→停留时间。各温差步骤分别向对应的热负荷步骤提供温差。`$ref`记录前序步骤、输出字段、数值与单位，传递过程使用完整精度。

工作台中的数值卡来自成功工具输出。点击工具步骤可查看实际参数及返回结果，点击引用可查阅知识原文；导出功能提供Markdown报告与JSON记录。知识资料库支持全文及来源查阅，工具注册表展示业务工具及本地MCP辅助工具。

本题cp与密度采用题目给定值。显热计算采用稳态单相恒比热模型。变比热问题使用热容函数及其有效温区进行焓积分，相变问题补充相态、操作压力、相变温度与相变焓；相关专业说明详见研究报告。

## 验证与交付

```bash
uv run pytest
node --test tests/frontend_state.test.cjs
uv run ruff check src tests scripts app.py cli.py
uv run ruff format --check src tests scripts app.py cli.py
cd src/chem_agent/web
npm test
npm run build
npm run lint
npm run format:check
```

测试覆盖质量与能量衡算、单位相容性、结果引用、参数来源、检索溯源、会话处理、报告导出及交付包内容。`tests/fixtures/regression_cases.json` 保存内部回归输入；`examples/tasks.json` 统一保存对外演示题目。

在项目根目录运行 `uv run python scripts/package.py` 生成 `dist/Chemical.zip` 与SHA256校验文件。源码包包含代码、依赖清单、知识资料、统一示例、测试、运行说明和研究报告。密钥、本机依赖、模型缓存及原始私有运行记录保存在使用方本机。

研究报告随项目交付材料提供，在本地保留，不纳入源码仓库。实际界面截图位于 `docs/validation/continuous/`，统一保存为PNG格式。

```text
src/chem_agent/        模型集成、执行器、计算、检索、API与报告导出
src/chem_agent/web/    Vue工作台
data/knowledge/      专业知识资料
examples/tasks.json   统一综合演示题目
tests/                自动化验证
scripts/              演示、验证与交付打包
docs/                 实际界面截图与演示记录
```
