# 化工知识与计算助手

一个可本机运行、可移交源码的教学演示系统：从 15 张化工知识卡检索依据，调用固定计算工具，并保留计划、参数、结果和来源。`0.2.0` 使用浏览器工作台；桌面视图中输入与结果并排显示，长内容在面板内滚动，无需到页面底部寻找答复。

## 能做什么

- **知识问答**：检索原文、来源和片段编号；相关性不足时说明资料不足。
- **单位换算**：常用质量、体积、流量、压力、温度及温差，拒绝不兼容量纲。
- **显热热负荷**：使用明确给出的质量流量、比热和温差，保留前序换算结果的真实引用。
- **混合衡算**：计算稳态、无反应混合物流的总质量流量及同一组分质量分数。
- **补充参数与导出**：在原任务上下文中补充数据，生成关联的新运行；导出 Markdown 报告和 JSON 记录。

资料均为项目自编教学说明，非实测物性。相变、反应热、复杂流程模拟和真实物性查询不在当前范围内。

## 安装与启动

需要 Python 3.11–3.13、`uv`；本机使用 Python 3.12。未安装 uv 时可运行 `python -m pip install uv`。首次安装依赖和调用模型需要联网。解压后在含 `pyproject.toml` 的目录执行：

```bash
uv sync --locked
cp .env.example .env
```

Windows PowerShell 将复制命令改为 `Copy-Item .env.example .env`。编辑本机 `.env`，选择一种密钥配置方式：

```dotenv
DEEPSEEK_API_KEY=填写自己的密钥
# 或保持上项为空，使用只存放密钥字符串的本机文本文件：
# DEEPSEEK_API_KEY_FILE=/absolute/path/to/your-key.txt
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
CHEM_PORT=7865
```

环境变量优先于 `.env`；直接设置的密钥优先于密钥文件。交付包不含可用密钥，接收方需配置自己的账号。

```bash
uv run chem-agent doctor
uv run chem-agent ui
```

按上述配置打开 `http://127.0.0.1:7865`；程序默认端口为 `7860`。端口冲突时修改 `CHEM_PORT`。也可用 `./start.sh`（macOS/Linux）或 `start.bat`（Windows）。前端为原生 HTML/CSS/JavaScript，由 FastAPI/uvicorn 提供页面和接口，无需 Node 或前端构建。启动时保持一个服务进程。

## 工作台操作

1. 选择示例或输入问题，点击“运行”（或 Ctrl/⌘ + Enter）。输入区和结果区保持在同一工作台内。
2. 在“结论”查看工具数值与模型说明；切换“过程”“依据”核对参数、引用和原文。数值卡取自成功工具输出。
3. 状态为“等待补充”时输入数据并点击“继续”。系统创建关联的新运行，按当前会话上下文重新规划；不恢复旧执行器。
4. 点击“停止”取消当前任务，待其结束后可“新建任务”。完成、缺参、资料不足、超范围、失败或取消的记录均可查看和导出。新建任务清空当前任务上下文，通过左侧任务记录可重新查看已结束的运行。

热负荷示例：`1000 kg/h`、`25→65 °C`、给定比热 `4.18 kJ/(kg·K)`，结果约 `46.44 kW`；流量改为 `2000 kg/h` 后约 `92.89 kW`。

同一浏览器会话通过 Cookie 关联，刷新页面可恢复服务内存中的当前状态。界面每个会话保留最近最多 40 轮，非活动会话闲置 24 小时后过期；服务重启后会话和界面历史不恢复，原始 `runs/` 文件仍保留。整个服务同时处理一个模型任务，忙时再次提交会提示稍后重试。当前面向本机演示，未验证生产多人部署。

取消会阻止后续工具调用；已经发出的模型请求可能等待返回或超时，其响应不会继续触发工具。单次请求超时默认 60 秒，可用 `CHEM_REQUEST_TIMEOUT` 调整。失败或取消前已经成功的步骤保留供复核，不表示整个任务成功。

## 常用命令

在项目根目录运行。`doctor`、`index`、`search` 和默认测试不调用模型。

| 命令 | 用途 |
| --- | --- |
| `uv run chem-agent doctor` | 检查 Python、资料数量和密钥是否配置；不验证远端认证或余额 |
| `uv run chem-agent index` | 重建资料索引并写入 `build/knowledge_manifest.json` |
| `uv run chem-agent search "显热热负荷计算"` | 离线检索知识卡 |
| `uv run chem-agent run "请将2.5 MPa换算成kPa。"` | 调用实际模型执行任务，消耗 API 额度 |
| `uv run chem-agent ui` | 启动本机工作台 |
| `uv run pytest` | 运行离线回归测试 |
| `node --test tests/frontend_state.test.cjs` | 可选前端状态回归；已使用 Node 24 验证，运行系统本身不需要 Node |
| `uv run python scripts/validate_live.py` | 重新执行 8 个真实模型案例，消耗 API 额度 |
| `uv run python scripts/package.py` | 生成 `dist/chem-agent-demo-0.2.0.zip` |

命令行补参时，用前一结果的 `run_id` 替换 `RUN_ID`；指定记录须存在于本机 `runs/`：

```bash
uv run chem-agent run "比热为4.18 kJ/(kg·K)，假设单相、恒比热且无热损失。" --follow-up RUN_ID
```

## 运行记录与维护

- **Markdown 报告**：用于阅读和移交，包含问题、答复、成功工具数值、执行计划、来源摘录和适用条件；不会额外请求模型。
- **JSON 记录**：用于详细复核，包含实际参数、结果引用、工具输出、状态和请求中的工具观察。每轮原始记录写入 `runs/<run_id>.json`。

模型请求证据省略私密推理，已知密钥会脱敏。记录仍可能含用户输入及业务数据，分享前应检查；脱敏不等于自动识别全部敏感业务信息。

```text
src/chem_agent/       模型、执行器、计算、检索、API 与报告导出
src/chem_agent/web/   浏览器工作台 HTML/CSS/JavaScript
data/knowledge/      可编辑的 Markdown 教学知识卡
examples/tasks.json  演示及真实验证题目
tests/               离线回归测试
scripts/             真实验证和白名单打包
docs/validation/     随包提供的验证证据
```

知识卡以 `# 标题` 和 `来源：…` 开头，正文可用 `##` 分段。修改后新任务从源文件重建索引；运行 `index` 更新资料清单，重启服务刷新页面资料库的清单和正文。不要将未核验的物性数值作为通用参数加入资料。交付包排除 `.env`、`.venv`、`.local` 和原始 `runs/`。

## 验证范围

`0.2.0` 已通过 **157 项 Python 离线测试、12 项前端状态测试**及 Ruff 检查。2026-10-02 在工作台发起三轮真实 DeepSeek 任务：缺参、补参和独立热负荷；两次计算均得到 **46.44 kW**。共 9 次模型请求成功，保留补参关联和换算结果引用。

浏览器已验证补参、标签切换、工具输入输出、资料浏览、Markdown/JSON 下载及刷新恢复。布局尺寸检查覆盖 `1440×852`、`662×745`、`390×796`，DOM 测量确认根页面未溢出，输入与结果区在视口内。独立解压复装通过：锁定依赖、无密钥环境检查、15 卡索引、157 项测试及页面资源/API 检查；wheel 含全部静态资源。

详见[检查记录](docs/validation/v0.2.0/checks.json)、[技术与验证报告](docs/技术与验证报告.md)及[工作台截图](docs/validation/v0.2.0/workbench.png)。旧版 8 个模型案例单独保留作历史记录。

未验证 Windows、完全离线模型、生产多人部署及未收录主题的准确率。工具输入仍需与用户给定参数核对。
