# 化工知识与计算助手

一个可本机运行、可移交源码的化工知识与计算演示系统。资料包括原有 21 张知识卡及新增 50 张来源可追溯的教学整理卡，共 71 张。新增资料覆盖单位与热容基准、能量衡算边界、组成换算、多组分混合、分流、循环和排放等主题，依据 NIST、IUPAC、MIT OCW、OpenStax、LearnChemE 和 Cantera 官方资料独立整理，不提供未经核验的实测物性常数。建好索引后，知识检索采用 LightRAG 的图谱与向量混合模式；工作台展示本轮实际检索路径、工具调用及数值引用。

## 能做什么

- **知识问答**：使用 LightRAG 检索实体关系与原文片段，保留来源和片段编号；索引未就绪时明确显示词法回退。
- **单位换算**：常用质量、体积、流量、压力、温度及温差，拒绝不兼容量纲。
- **显热热负荷**：使用明确给出的质量流量、比热和温差，保留前序换算结果的真实引用。
- **混合衡算**：计算稳态、无反应混合物流的总质量流量及同一组分质量分数。
- **补充参数与导出**：在原任务上下文中补充数据，生成关联的新运行；导出 Markdown 报告和 JSON 记录。

来源卡不是物性数据库，不能自动填入比热等工况参数。相变、反应热、复杂流程模拟和真实物性查询不在当前范围内。

当前交付版本为 **0.3.2**，按现有七项合同摘要组织实现与验收：[能力映射](docs/CONTRACT_COMPLIANCE.md)、[实际架构](docs/ARCHITECTURE.md)、[全库审查与改造依据](docs/AUDIT_AND_PLAN.md)。系统为一套 Agent 工作流，没有独立多 Agent 协作功能。

## 不用密钥的演示

安装后可以直接执行固定离线流程：

```bash
uv run python scripts/demo_offline.py
uv run python scripts/demo_offline.py --flow 2000
```

真实执行本地资料检索、工具注册表、流量换算、带单位的结果引用和显热计算，分别得到约 **46.44 kW / 92.89 kW**；JSON 和 Markdown 写入忽略目录 `runs/`。记录明确标为 `offline_demo`。此路径不读取密钥，不调用模型或 LightRAG，不证明模型能够自行规划。知识问答及模型驱动的多工具流程按下文配置接收方自己的密钥运行。

## 安装与启动

### 本机前后端分别启动（Conda + Vue）

在已安装依赖的本机，打开两个终端，分别执行：

```bat
cd /d "E:\Python PyCharm\chem-agent"
conda activate chem-agent
python app.py
```

```bat
cd /d "E:\Python PyCharm\chem-agent\src\chem_agent\web"
npm run dev
```

日常使用 Vue 问答工作台 `http://127.0.0.1:5173/`。它通过 `/api` 代理访问 `7860`，采用独立入口 `web/client/index.html`，组件、状态管理、API 请求和类型分别位于 `web/src/`。`7860` 的原生演示页面保留，两个页面各自启动，Vue 页面不加载后端 HTML。后端端口改变时需同步修改 `web/vite.config.ts` 中的代理目标。

前端沿用 Vue 3、TypeScript、Vite 和本地图标资源，视觉参照 shadcn 工作台布局；未引入 React。无 CDN、远程字体或外部 UI 资源依赖。迁移后在 `web` 执行 `npm ci` 安装锁定依赖，或恢复同平台离线依赖包中的 `node_modules`。`npm run build` 输出 `web/dist`，`npm run preview` 可在 `4173` 检查生产构建，同时仍需启动后端。前端离线资源可用不表示模型推理可离线运行。

源码提交包含 `client`、`src`、前端测试及 package/lock/config 文件；`node_modules`、构建产物、缓存和密钥不提交。下文保留后端的 uv 安装、索引构建及原生演示操作方式。

### 后端依赖与模型配置

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
CHEM_PORT=7860
```

环境变量优先于 `.env`；直接设置的密钥优先于密钥文件。交付包不含可用密钥，接收方需配置自己的账号。

密钥文件必须在接收方本机存在且可读。若报“无法读取 DEEPSEEK_API_KEY_FILE”，修正本机路径，或清空该项后配置 `DEEPSEEK_API_KEY`；源码包不携带开发机密钥文件。

```bash
uv run chem-agent doctor
uv run chem-agent rag-index
uv run chem-agent ui
```

`rag-index` 首次运行会下载约 90 MB 的本地中文向量模型，并用 DeepSeek 以中文从当前资料抽取实体关系；需要网络、有效密钥并消耗 API 额度。索引持久保存于忽略目录 `build/lightrag/`，源码交付包不包含它。资料有变化后重新执行该命令；`uv run chem-agent rag-status` 可离线检查是否就绪。未建索引时仍可运行旧的词法检索，工作台会标明当前后端。普通 LightRAG 查询也可能调用 DeepSeek 做关键词抽取，其请求不计入主代理的 `model_requests` 数量。

按上述配置打开 `http://127.0.0.1:7860`；程序默认端口为 `7860`。端口冲突时修改 `CHEM_PORT`，并同步修改 Vue 的代理目标。也可用 `./start.sh`（macOS/Linux）或 `start.bat`（Windows）。此地址上的原生演示页面由 FastAPI/uvicorn 提供，无需 Node；独立 Vue 工作台按上节启动。后端保持一个服务进程。

## 工作台操作

前端“依据与过程”展示当前问答的实际处理数据：检索路径提供主题词、细节词、实体关系和原文；执行审计提供计划、模型选用工具、调用参数、步骤状态、前序结果回用、原文入模匹配和耗时；引用依据提供回答引用的知识片段。知识资料库支持查阅正文、分段与来源。数值卡和答复来自实际执行结果。

演示时可先运行一个“混合→单位换算→加热”的组合任务，再运行一个专业知识问答，通过页面中的处理阶段、时间线和引用说明核对主流程。发送问题后才调用配置的模型API，工具注册表中的MCP辅助工具由用户手动试用。当前浏览器演示及记录见`docs/项目验收证据.md`。开发人员可按需使用`python -m scripts.validate_live --case mixed_heat --backend lightrag --output runs/live-check.json`作指定案例的额外验证。

Vue 工作台右侧的“执行审计”展示工具选择计划、前序依赖、模型返回的工具动作、实际调用参数与结果、耗时及 Token 用量。统计范围为 Agent 主流程；历史记录缺少的字段显示“未记录”。模型事件仅公开动作与计量摘要。

右侧标题栏的“工具注册表”列出四类 Agent 业务工具和三个本地 MCP 辅助工具：单位量纲检查、质量流量闭合检查、知识资料来源查询。辅助工具使用 MCP stdio 发现与调用，在面板中填写 JSON 参数即可手动试用；结果标为手动调用，保留最近十次页面记录。现有模型业务流程沿用原工具链。MCP 服务由后端按需启动，无需额外端口、密钥或单独启动命令。新增依赖已锁定为 `mcp==1.26.0`。

1. 输入问题，或选用一个问题模板，点击“运行”（或 Ctrl/⌘ + Enter）。输入区和结果区保持在同一工作台内。
2. 在“结论”查看工具数值与答复；切换“路径”“调用”“依据”核对真实命中的实体、关系、片段、来源，以及调用参数与结果引用。数值卡取自成功工具输出。
3. 状态为“等待补充”时输入数据并点击“继续”。系统创建关联的新运行，按当前会话上下文重新规划；不恢复旧执行器。
4. 点击“停止”取消当前任务，待其结束后可“新建任务”。完成、缺参、资料不足、超范围、失败或取消的记录均可查看和导出。新建任务清空当前任务上下文，通过左侧任务记录可重新查看已结束的运行。

热负荷示例：`1000 kg/h`、`25→65 °C`、给定比热 `4.18 kJ/(kg·K)`，结果约 `46.44 kW`；流量改为 `2000 kg/h` 后约 `92.89 kW`。

同一浏览器会话通过 Cookie 关联，刷新页面可恢复服务内存中的当前状态。界面每个会话保留最近最多 40 轮，非活动会话闲置 24 小时后过期；服务重启后会话和界面历史不恢复，原始 `runs/` 文件仍保留。整个服务同时处理一个模型任务，忙时再次提交会提示稍后重试。当前面向本机演示，未验证生产多人部署。

页面为每次提交生成请求编号；提交响应丢失时可恢复这次已经结束或仍在执行的结果，手工重试也沿用原编号，避免重复执行。幂等记录只在当前会话最近 40 条历史内有效，重启或会话过期后不保留。

热负荷可以引用前序混合衡算的总流量或组分流量，执行器核对依赖和单位后转换为 `kg/s`。有流量换算依赖时仍须用 `$ref`，避免重新抄写数值。

模型驱动的热负荷计算会核对比热是否来自当前问题或用户补参历史中的明确数值和单位，教学算例及助手答复不能充当给定物性。支持 `J/(kg·K)`、`kJ/(kg·K)` 及摄氏温差单位，例如 `4180 J/(kg·K)` 归一化为 `4.18 kJ/(kg·K)`。最新明确给定值覆盖旧值；缺少单位的改值、明确未知或撤回不能重新启用旧值。匹配成功后，调用记录的 `input_provenance` 保存用户消息位置、归一化数值和单位。缺参、冲突或不支持的表达会阻止计算并要求补充。这是针对质量比热的窄表达匹配，其他参数及任意自然语言中的归因仍需人工核对。

已完成计算的 `answer` 由成功工具的数值、输入和全部适用条件生成，展示最多 12 位有效数字，计算保留原始精度；不会把舍入后的中间值拼成精确等式。JSON 的 `model_answer` 保存原模型答复供审计，`answer_source="verified_tools"` 标明纯计算答复来源。当前问题明确要求解释、区别或原理等内容时，`set_plan` 要求计算计划包含检索，`complete` 要求成功检索、真实引用和非空 `explanation` 后才允许完成；仅把解释写在模型的 `answer` 中不能通过。纯计算的旧最终工具接口仍可省略 `explanation`。

复合问题的解释保留在生成答复中，标为 `verified_tools_with_explanation`，原输入另存 `model_explanation`。定性说明可与不同已引用片段的定量原文逐句组合；含数值关系、运算或计算结果的每句必须逐字匹配本轮已引用原文，并标为“来源原文（非本轮计算结果）”。不匹配的定量说明被拒绝，模型可改写后重试。解释请求识别、表达形式和原文匹配均为有限规则，不证明任意知识结论的语义正确。知识问答、缺参或失败说明仍保留模型答复。图谱关联来源是索引中的来源集合，需展开原文逐条核对合并描述。

取消会阻止后续工具调用；已经发出的模型请求可能等待返回或超时，其响应不会继续触发工具。单次请求超时默认 60 秒，可用 `CHEM_REQUEST_TIMEOUT` 调整。失败或取消前已经成功的步骤保留供复核，不表示整个任务成功。

## Docker 与接口

需要 Docker 和 Compose。镜像固定基础镜像摘要、按 `uv.lock` 安装依赖、以非 root 用户运行。Compose 从项目 `.env` 读取**直接密钥** `DEEPSEEK_API_KEY`，宿主机密钥文件路径不会自动挂入容器。无密钥也能启动页面和健康检查，模型任务会明确失败；也可在容器执行离线演示。

```bash
docker compose up --build -d
curl http://127.0.0.1:7860/health
docker compose exec chem-agent python scripts/demo_offline.py
# 启用真实图谱（需要密钥，会下载模型并消耗 API 额度）
docker compose exec chem-agent chem-agent rag-index
docker compose down
```

端口默认为 `7860`；`.env` 中的 `CHEM_PORT` 只改变宿主机映射端口，容器内部固定为 `7860`。命名卷分别保存记录、索引和向量模型缓存，down 不删除它们。镜像构建上下文与源码包都不包含 `.env`、本机索引、模型缓存或私有记录。

| 接口 | 用途 |
|---|---|
| `GET /health` | 服务存活、版本、密钥配置布尔值和检索后端；不分配 Cookie，不验证远端认证/余额 |
| `GET /api/bootstrap`、`GET /api/session` | 页面资料/示例/索引状态与当前会话历史 |
| `POST /api/jobs` | `question`（1–4000字）、可选 `parent_job_id`、可选32位小写十六进制 `client_request_id`；返回202 |
| `GET /api/jobs/{job_id}` | 当前状态、计划、实际调用与证据；轮询到 finished |
| `POST /api/jobs/{job_id}/cancel` | 请求取消当前会话任务 |
| `GET /api/jobs/{job_id}/report.md`、`trace.json` | 下载终态报告/追溯；未结束返回409 |
| `GET /api/knowledge/{doc_id}` | 查看实际知识卡 |

API 为本机工作台服务；同会话用 Cookie，写入请求须提供与访问地址相同的 Origin。相同请求编号和相同输入返回原任务；复用编号修改输入返回409。422表示输入格式错误，404表示任务/资料不存在或不属于当前会话，403表示访问地址/Origin不允许。每个响应含 `X-Request-ID`；日志只记录路由、编号、状态和延迟，不记录问题正文。

```bash
mkdir -p .local
curl -c .local/api-cookies.txt http://127.0.0.1:7860/api/bootstrap
curl -b .local/api-cookies.txt -H 'Origin: http://127.0.0.1:7860' \
  -H 'Content-Type: application/json' \
  -d '{"question":"请将2.5 MPa换算成kPa。","client_request_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}' \
  http://127.0.0.1:7860/api/jobs
```

用返回的 job_id 查询结果。每个新输入需使用新的 client_request_id；示例的固定编号用于演示重试。

## 常用命令

在项目根目录运行。`doctor`、`index`、`search`、`rag-status` 和默认测试不调用模型；`rag-index`、工作台任务以及已就绪索引上的 LightRAG 查询可能调用 DeepSeek。

| 命令 | 用途 |
| --- | --- |
| `uv run chem-agent doctor` | 检查 Python、资料数量和密钥是否配置；不验证远端认证或余额 |
| `uv run chem-agent index` | 更新离线词法检索资料清单 `build/knowledge_manifest.json` |
| `uv run chem-agent search "显热热负荷计算"` | 离线词法检索知识卡 |
| `uv run chem-agent rag-index` | 构建 LightRAG 图谱与向量索引，下载向量模型并调用 DeepSeek |
| `uv run chem-agent rag-status` | 离线检查当前资料对应的 LightRAG 索引状态 |
| `uv run chem-agent run "请将2.5 MPa换算成kPa。"` | 调用实际模型执行任务，消耗 API 额度 |
| `uv run chem-agent ui` | 启动本机工作台 |
| `uv run pytest` | 运行离线回归测试 |
| `node --test tests/frontend_state.test.cjs` | 可选前端状态回归；已使用 Node 24 验证，运行系统本身不需要 Node |
| `uv run python scripts/validate_live.py` | 执行原 8 案例、混合后加热及温度换算解释，共 10 案例；核对工具引用、答复数值/单位/条件与解释，消耗 API 额度 |
| `uv run python scripts/package.py` | 生成带版本号的源码交付 ZIP |

真实验收可用 `--index-root /path/to/project --backend lightrag` 复用知识版本相同且已就绪的索引和向量缓存，仍使用当前项目的代码、模型配置、知识卡与 `runs/`。`--backend auto` 使用实际可用后端；`--backend lexical` 要求索引未就绪，已就绪时会在模型调用前报错。报告记录所测提交、源码哈希和实际检索后端，并单独统计被拒工具批次、工具错误及最终答复重试；恢复标志只说明执行终态，仍须通过该案例的业务验收。

命令行补参时，用前一结果的 `run_id` 替换 `RUN_ID`；指定记录须存在于本机 `runs/`：

```bash
uv run chem-agent run "比热为4.18 kJ/(kg·K)，假设单相、恒比热且无热损失。" --follow-up RUN_ID
```

## 运行记录与维护

- **Markdown 报告**：用于阅读和移交，包含问题、答复、成功工具数值、执行计划、来源摘录和适用条件；不会额外请求模型。
- **JSON 记录**：用于详细复核，包含实际参数、结果引用、工具输出、状态和请求中的工具观察。每轮原始记录写入 `runs/<run_id>.json`。

模型请求证据省略私密推理，已知密钥会脱敏。记录仍可能含用户输入及业务数据，分享前应检查；脱敏不等于自动识别全部敏感业务信息。

运行模式区分模型驱动的 `live`、固定离线演示的 `offline_demo`，以及模型尚未开始的 `not_started`。无密钥等启动失败可以导出记录，但不作为真实模型验证；请求次数以 JSON 中保存的实际记录为准。

```text
src/chem_agent/       模型、执行器、计算、检索、API 与报告导出
src/chem_agent/web/   浏览器工作台 HTML/CSS/JavaScript
data/knowledge/      可编辑的 Markdown 教学知识卡
examples/tasks.json  演示及真实验证题目
tests/               离线回归测试
scripts/             真实验证和白名单打包
docs/validation/     随包提供的验证证据
```

知识卡以 `# 标题` 和 `来源：…` 开头，正文可用 `##` 分段。修改资料后运行 `rag-index` 重建 LightRAG 索引；运行 `index` 更新离线资料清单，重启服务刷新页面资料库的清单和正文。不要将未核验的物性数值作为通用参数加入资料。交付包排除 `.env`、`.venv`、`.local`、`build/` 和原始 `runs/`。选型、来源及证据边界见[检索与工具链升级说明](docs/检索与工具链升级.md)。

新增知识卡由现有目录扫描机制自动纳入资料库和离线检索，无需修改前端或后端接口。知识扩充不会自动增加计算工具：目前数值工具仍仅支持已列出的兼容单位换算、恒比热显热负荷、稳态无反应混合衡算。摩尔组成换算、变比热积分、相变、分离和循环求解等卡片用于解释定义与适用边界，不能据此声称已经实现这些数值功能。LightRAG 索引与知识文件的版本绑定；旧索引过期后显式回退词法检索，重建命令会调用模型并产生 API 用量。

同一相对位置不得同时存在同 stem 的 `.md` / `.txt` 文件，避免重复文档与引用编号。索引校验包含向量解码、维度、记录匹配、有限值和完整 GraphML 解析；LightRAG 的共享存储按目录及资料版本隔离，保留0.3.0已有磁盘结构。

## 验证与交付证据

功能演示直接在Vue问答工作台进行：输入任务后，查看“检索路径”“执行审计”“引用依据”，展开条目核对实际参数、返回值、来源和数值回用。当前演示的问题、预期结果、真实运行记录与截图见[项目验收证据](docs/项目验收证据.md)。

本机离线检查包括Python回归测试、Vue前端测试、类型检查、生产构建、Lint及格式检查。Python测试在Windows中文系统中使用UTF-8运行模式，确保主进程和测试子进程采用同一编码：

```powershell
$env:PYTHONUTF8='1'
python -m pytest -q
cd src/chem_agent/web
npm run typecheck
npm run lint
npm run format:check
npm test
npm run build
```

源码包使用 `python scripts/package.py` 生成 `dist/chem-agent.zip` 及SHA256校验文件。压缩包根目录为 `chem-agent/`，保留代码、知识资料、配置样例、依赖锁文件、启动说明、案例、研究报告和流程演示证据；排除本机环境、API密钥、node_modules、模型缓存、索引和私有运行记录。接收方按说明安装锁定依赖，配置自己的API密钥并构建LightRAG索引后，可运行问答流程。

`docs/validation/v*/`保存历史验证记录，其代码和数据以各自记录为准。当前前端流程演示存放在`docs/validation/workflow/`。
