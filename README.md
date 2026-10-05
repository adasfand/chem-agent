# 化工知识与计算助手

一个可本机运行、可移交源码的教学演示系统：从 15 张化工知识卡检索依据，调用固定计算工具，并保留计划、参数、结果和来源。前端使用 Vue 3、TypeScript 和 Vite，后端使用 FastAPI 与 smolagents；前后端分别启动，前端通过 `/api` 代理访问后端服务。当前为 Vue 前端改造的开发版本，前端包版本独立于后端 `0.2.0`，尚不代表正式合同验收完成。

## 能做什么

- **知识问答**：检索原文、来源和片段编号；相关性不足时说明资料不足。
- **单位换算**：常用质量、体积、流量、压力、温度及温差，拒绝不兼容量纲。
- **显热热负荷**：使用明确给出的质量流量、比热和温差，保留前序换算结果的真实引用。
- **混合衡算**：计算稳态、无反应混合物流的总质量流量及同一组分质量分数。
- **补充参数与导出**：在原任务上下文中补充数据，生成关联的新运行；导出 Markdown 报告和 JSON 记录。

资料均为项目自编教学说明，非实测物性。相变、反应热、复杂流程模拟和真实物性查询不在当前范围内。

## 安装与启动

后端使用名为 `chem-agent` 的 Conda 环境，Python 3.12；`uv.lock` 锁定 Python 依赖。以下是 Windows PowerShell 首次安装命令，在含 `pyproject.toml` 的项目根目录执行。已有环境时跳过创建：

```powershell
conda create -n chem-agent python=3.12 pip -y
conda activate chem-agent
uv export --locked --format requirements-txt --no-emit-project --output-file "$env:TEMP\chem-agent-requirements.txt" > $null
python -m pip install -r "$env:TEMP\chem-agent-requirements.txt"
python -m pip install --no-deps -e .
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

使用本机已有 Conda、uv 和 Node，不安装全局 npm 组件。前端依赖及安装目录全部位于 `src/chem_agent/web/`，首次安装依赖需要联网。编辑根目录 `.env`，选择一种密钥配置方式：

```dotenv
DEEPSEEK_API_KEY=填写自己的密钥
# 或保持上项为空，使用只存放密钥字符串的本机文本文件：
# DEEPSEEK_API_KEY_FILE=/absolute/path/to/your-key.txt
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
CHEM_PORT=7860
```

环境变量优先于 `.env`；直接设置的密钥优先于密钥文件。交付包不含可用密钥，接收方需配置自己的账号。

```powershell
conda activate chem-agent
python cli.py doctor
python app.py
```

后端 API 默认监听 `http://127.0.0.1:7860`，健康检查地址为 `http://127.0.0.1:7860/api/health`。`doctor` 仅检查配置，不验证模型认证或余额。也可用 `start.bat`（Windows）或 `./start.sh`（macOS/Linux）；脚本使用同名 Conda 环境，不自动安装依赖。PyCharm 解释器应指向该环境的 `python.exe`。

保持后端终端运行，另开终端启动前端（本机已安装依赖，可直接执行 `npm run dev`）：

```powershell
Set-Location "E:\Python PyCharm\chem-agent\src\chem_agent\web"
# 首次安装或 package-lock.json 更新后执行 npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`，Vite 将 `/api` 请求代理到 `127.0.0.1:7860`；使用这两个一致的本机地址。改动后端端口时同步修改 `web/vite.config.ts` 中的代理目标。Node 版本要求见 `web/package.json` 的 `engines` 字段。所有前端代码、测试、配置、锁文件和 `node_modules` 都保留在 `web/` 中。

日常启动使用后端 `python app.py` 和前端 `npm run dev` 两个终端，页面入口为 `http://127.0.0.1:5173`。需要检查前端编译产物时，在 `web/` 运行 `npm run build`，再运行 `npm run preview`，打开 `http://127.0.0.1:4173`；预览服务同样代理 `/api` 到后端，仅用于本机检查。页面脚本、样式和图标均由前端提供，不从 CDN 加载。DeepSeek 推理仍需联网和有效密钥。

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
| `python cli.py doctor` | 检查 Python、资料数量和密钥是否配置；不验证远端认证或余额 |
| `python cli.py index` | 重建资料索引并写入 `build/knowledge_manifest.json` |
| `python cli.py search "显热热负荷计算"` | 离线检索知识卡 |
| `python cli.py run "请将2.5 MPa换算成kPa。"` | 调用实际模型执行任务，消耗 API 额度 |
| `python app.py` | 启动本机后端 API 服务 |
| `python -m pytest` | 运行离线 Python 回归测试 |
| `npm run typecheck` / `npm run lint` / `npm run format:check` / `npm test` | 在 `web/` 执行前端类型、规范、Prettier 格式及 Vitest 检查 |
| `npm run build` | 在 `web/` 编译交付页面到 `dist/` |
| `python scripts/validate_live.py` | 重新执行 8 个真实模型案例，消耗 API 额度 |
| `python scripts/package.py` | 打包源码、知识卡和前端项目；若已有前端构建产物则一并包含 |

命令行补参时，用前一结果的 `run_id` 替换 `RUN_ID`；指定记录须存在于本机 `runs/`：

```bash
python cli.py run "比热为4.18 kJ/(kg·K)，假设单相、恒比热且无热损失。" --follow-up RUN_ID
```

## 运行记录与维护

- **Markdown 报告**：用于阅读和移交，包含问题、答复、成功工具数值、执行计划、来源摘录和适用条件；不会额外请求模型。
- **JSON 记录**：用于详细复核，包含实际参数、结果引用、工具输出、状态和请求中的工具观察。每轮原始记录写入 `runs/<run_id>.json`。

模型请求证据省略私密推理，已知密钥会脱敏。记录仍可能含用户输入及业务数据，分享前应检查；脱敏不等于自动识别全部敏感业务信息。

```text
src/chem_agent/       模型、执行器、计算、检索、API 与报告导出
src/chem_agent/web/   Vue / TypeScript 源码、配置、测试及 npm 锁文件
  src/              前端组件、API 客户端、状态和样式
  dist/             可离线提供的编译页面（构建生成）
  node_modules/     本机前端开发依赖（安装生成）
data/knowledge/      可编辑的 Markdown 教学知识卡
examples/tasks.json  演示及真实验证题目
tests/               离线回归测试
scripts/             真实验证和白名单打包
docs/validation/     随包提供的验证证据
```

知识卡以 `# 标题` 和 `来源：…` 开头，正文可用 `##` 分段。修改后新任务从源文件重建索引；运行 `index` 更新资料清单，重启服务刷新页面资料库的清单和正文。不要将未核验的物性数值作为通用参数加入资料。

源码交付包包含前端源码、`package-lock.json` 及已有的可选 `web/dist`，排除 `.env`、虚拟环境、`node_modules`、开发缓存、`.local` 和原始 `runs/`。Python wheel 仅分发后端 Python 包，前端项目通过源码 ZIP 单独提供。每个交付 ZIP 附带 SHA-256 文件。

前端依赖包独立于源码包，包含本机 `node_modules`、npm 锁文件及平台清单，不包含 Node 安装程序。离线接收方需自行提供兼容 Node，核对相同 Windows/CPU 架构、Node 版本以及 `offline-dependencies.json` 中锁文件哈希后，再将依赖包中的 `node_modules` 解压到对应项目的 `web/`；不要覆盖不同版本项目的锁文件。使用 `npm run dev` 或 `npm run preview` 时需要前端 Node 环境与 `node_modules`。Python 离线安装环境不包含在这两个 ZIP 中。

## 验证范围

2026-10-05 完成 API 独立启动调整：25 项 API/打包回归测试及 Ruff 检查通过；实际启动后端 `7860` 和前端 `5173`，验证 Vue 页面、15 张知识卡、会话及代理校验正常，浏览器控制台无错误。后端页面与静态资源路由返回 404；Python wheel 已核对只包含后端包。本次未调用真实模型 API。

2026-10-04 完成 Windows 本机检查：Conda `chem-agent` / Python 3.12.14。前后端分离阶段 **161 项 Python 测试**通过；随后界面优化阶段通过 **33 项前端测试、23 项后端 UI/API 回归测试**。TypeScript、ESLint、Prettier 及最新前端构建通过，Python 分离阶段 Ruff 检查通过。前端 8 项业务请求均与后端接口对应。浏览器通过离线测试模型驱动真实本地检索与计算工具，检查热负荷、前序结果引用、补参关联、取消、刷新恢复、知识卡浏览和两种导出；桌面、平板及手机尺寸无横向溢出，控制台无错误。最新源码 ZIP 已更新；独立前端依赖 ZIP 沿用已核验版本，依赖未变。界面见[当前页面](docs/validation/vue-local/workbench.png)。

界面优化保留重新连接时的输入草稿，后台标签页降低轮询频率，知识卡缓存合并重复请求并支持失败重试。工作台采用工程计算布局，区分公式示例与实际计算结果；平板与手机使用纵向布局，知识卡正文去除重复标题和来源。

本轮未配置可用 DeepSeek Key，未发起真实模型请求。离线测试入口只在开发检查中临时使用，不属于正式应用的运行模式。

以下为改造前 `0.2.0` 的历史验证记录，不代表当前 Vue 前端已通过真实模型验收：旧版通过 **157 项 Python 离线测试、12 项前端状态测试**及 Ruff 检查。2026-10-02 在旧工作台发起三轮真实 DeepSeek 任务：缺参、补参和独立热负荷；两次计算均得到 **46.44 kW**。共 9 次模型请求成功，保留补参关联和换算结果引用。

旧版浏览器验证覆盖补参、标签切换、工具输入输出、资料浏览、Markdown/JSON 下载及刷新恢复。旧版布局尺寸检查覆盖 `1440×852`、`662×745`、`390×796`；独立解压复装检查覆盖锁定依赖、无密钥配置、15 卡索引、157 项测试及页面资源/API。

详见[检查记录](docs/validation/v0.2.0/checks.json)、[技术与验证报告](docs/技术与验证报告.md)及[工作台截图](docs/validation/v0.2.0/workbench.png)。旧版 8 个模型案例单独保留作历史记录。

当前 Vue 改造的本机检查应区分 Python 离线测试、前端测试/构建、浏览器交互和真实模型调用；前三项不能替代真实 API 验证。完全离线模型、生产多人部署及未收录主题的准确率不在当前验证范围内。工具输入仍需与用户给定参数核对。
