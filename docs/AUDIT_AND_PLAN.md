# 当前系统审查、差距分析与改造计划

核对日期：2026-10-07。基线提交：`699f61b`；本轮交付版本：`0.3.1`。

## 范围依据

本轮以仓库保存的现有合同摘要为范围，目标是完整、可运行、可演示、可测试、可移交的交付物。依据为仓库初步方案第 2 节列出的七项要求，摘录随包保存于 [CONTRACT_SCOPE.md](CONTRACT_SCOPE.md)。本轮未取得扫描合同原件，不声称重新逐页审阅或作出法律验收判断。资料量、框架、前端、Docker 和测试数量属于工程选择。

## 当前架构与覆盖

现有代码是一个单进程 Python 系统：FastAPI 工作台和 CLI 共用 `run_task`；smolagents 选择注册工具；`Execution` 校验计划、依赖、参数与单位；计算函数独立于模型；LightRAG 实现已接入 `search_knowledge`，索引缺失时显示词法回退。21 张资料卡中 15 张自编、6 张有官方出处。补参创建关联的新运行，JSON 持久化，Markdown 从已有结果生成。

审查覆盖全部 `src/chem_agent/`、前端、配置、入口、示例、脚本、测试、README、报告与历史验证；查看了分支和四次现有提交。没有找到独立 Docker、数据库服务或多 Agent 实现，系统也未宣称提供这些能力。未把框架文档中可用的能力当作本项目已经实现的能力。

基线离线检查：174 项 Python、15 项 Node 状态测试、Ruff lint/format 均通过。测试通过仍遗漏了下列实际边界。

## 合同摘要与差距

| 摘要要求 | 当前实现 | 审查时状态 | 差距 | 本轮方案 | 优先级 |
|---|---|---|---|---|---|
| 知识资源组织、解析、分段、索引 | MD/TXT 加载、按节分段、词法索引、LightRAG 持久索引 | 基本实现 | 同 stem 文件和大写扩展名会误配来源；损坏向量/图谱可能被标为就绪 | 精确来源映射、重名拒绝、完整存储校验 | P1/P2 |
| 知识检索与上下文增强 | 主流程 `search_knowledge`，观察回传模型 | 基本实现 | SDK 全局 KV 缓存会在同进程跨索引串用旧数据 | 在固定 SDK 生命周期内隔离共享命名空间，保留磁盘结构 | P1 |
| 输入到检索到生成的完整路径 | Agent、API、引用、导出已联通 | 基本实现 | 一个空检索分支可被其他命中掩盖；缺少独立冒烟说明 | 完成条件检查各检索结果；提供离线固定流程与真实调用入口 | P2 |
| 复杂任务解析与规划 | 1–6 步结构化计划、依赖、有限 Agent 步数 | 基本实现 | 多工具同批可先产生副作用；最终工具可重写终态 | 执行前拒绝多工具批次、终态保护 | P2 |
| 多工具选择、执行与结果回用 | 检索、换算、热负荷、混合衡算；带单位 `$ref` | 基本实现 | 自由文本参数来源和最终说明仍需人工核对 | 保留真实输出数值卡和报告，明确不保证通用语义一致性 | 边界保留 |
| 核心源码、配置、依赖、运行和示例交付 | 锁定依赖、白名单 ZIP、启动脚本、CLI/工作台 | 基本实现 | 丢失提交响应可能重复付费；资料切换竞态；缺健康检查和容器入口 | 请求幂等与恢复、资料响应版本保护、health/日志/Docker、复装检查 | P2 |
| 与实物一致的研究报告 | 历史报告和 0.3.0 检索说明已有 | 部分实现 | 主要验收表仍标 0.2.0，缺统一当前架构/摘要映射 | 当前架构、合同符合性、研究报告更新和验证清单 | P2 |

不使用主观百分比掩盖缺口。七项均有真实实现，审查时尚需边界修复和当前交付证据；没有发现必须新增另一套 Agent/RAG 框架的 P0 缺口。

## 具体审查问题及修复方向

| 问题 | 位置 | 原因与影响 | 修复/验证 |
|---|---|---|---|
| [P1] 跨索引共享旧 KV | `retrieval._make_rag` | SDK 默认空 workspace；跨版本目录初始化仍返回旧 chunk | 独立 workspace，真实 SDK 存储初始化回归 |
| [P2] 损坏索引仍 ready | `retrieval._validate_index_stores` | 只检查 matrix 为字符串及 GraphML 头；SDK 随后加载失败 | 解码并校验向量形状/有限值、完整解析图谱；失败回退 |
| [P2] 来源卡误归属 | `knowledge.__init__`、`retrieval._source_catalog` | 去扩展名后重名覆盖，虚构 .md/.txt 映射遗漏大写扩展名 | 保存真实 file_path，拒绝重复 doc_id，精确对应出处 |
| [P2] 空检索仍宣告完成 | `Execution.execute/complete` | 全局 evidence 可掩盖必要分支未命中 | 阻止依赖空检索的计算及整轮 completed，允许修正查询重试 |
| [P2] 最终状态可重写 | `Execution.complete`、Agent 工具批次入口 | 多 final 或 final 与业务工具同批先执行后被框架拒绝 | 执行前拒绝批次、终态不可重复提交 |
| [P2] 丢失提交响应后遗漏已完成结果 | `ui._Runtime.start`、前端 `submit` | 只恢复 active_job_id，快速完成后它为 null | 可选 client_request_id 的会话内幂等及精确恢复 |
| [P2] 资料迟到响应覆盖最后选择 | 前端 `openKnowledge` | 请求响应未检查选择版本 | 最新选择优先的版本检查与状态回归 |

问题均使用离线输入实际复现。数值公式及常规单位转换没有发现高信号错误。未捕获异常、模型超时、错误脱敏、取消、量纲、跨会话导出等已有回归基础继续沿用。

## 技术调研与可复用代码

本轮查阅官方文档与代码，以下兼容性和成本判断针对本项目，不代表统一性能评测。

| 技术 | 当前/候选版本 | 用途与可复用起点 | 成熟度与成本 | 兼容性/许可 | 决定 |
|---|---|---|---|---|---|
| smolagents | 1.26.0（现有） | [ToolCallingAgent 与回调](https://huggingface.co/docs/smolagents/v1.26.0/en/reference/agents) | 官方维护；API 仍有变动风险，已锁定；沿用成本低 | 已真实接入；[Apache-2.0](https://github.com/huggingface/smolagents/blob/v1.26.0/LICENSE) | 直接复用，保留业务校验封装 |
| LightRAG | 1.5.7（现有） | [官方 OpenAI 接入例](https://github.com/HKUDS/LightRAG/blob/v1.5.7/examples/lightrag_openai_demo.py)、结构化 query_data | 官方维护；首次构图需外部模型，SDK 存储适配须回归 | 已真实接入；[MIT](https://github.com/HKUDS/LightRAG/blob/v1.5.7/LICENSE) | 沿用，不重复建设图谱 RAG |
| FastEmbed | 0.8.1（锁定） | 本地中文向量化，现有 EmbeddingFunc adapter | 官方维护；无向量服务，集成成本低 | 与当前 512 维索引匹配；[Apache-2.0](https://github.com/qdrant/fastembed/blob/main/LICENSE) | 沿用已验证模型 |
| FastAPI / Pydantic | 0.141.1 / 2.13.5（锁定） | 请求 schema、HTTP 与输入校验；[官方容器例](https://fastapi.tiangolo.com/deployment/docker/) | 文档完整；原项目已用，新增健康检查成本低 | MIT；无需新服务 | 直接沿用 |
| uv + Docker | uv 0.12.20、Python 3.12 容器 | [官方 uv Docker 指南](https://docs.astral.sh/uv/guides/integration/docker/)：锁定安装、分层复制 | 现有 uv.lock 可复用；增加一份容器入口 | 镜像不含密钥、索引或原始记录；源码非公开发布 | 采用简单单服务镜像 |
| LangGraph | 候选，未安装 | [checkpoint / persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | 官方维护；持久恢复有价值，当前迁移成本高于收益 | 需替换/扩展现有状态模型 | 暂不采用，后续确需恢复再评估 |

没有新增 Python 运行依赖；未复制整套 starter。框架仍负责通用工具循环/检索，领域公式、单位、来源、计划与交付约束由现有项目代码承担。可观测性使用标准 logging 与现有 JSON trace，当前不引入外部追踪账号或额外数据库。

## 实施文件与验收

P1：修改 `knowledge.py`、`retrieval.py` 及来源/索引测试。P2：修改 `agent.py`、`execution.py`、`model.py`、`tools.py`、`trace.py`、`ui.py`、前端及对应回归；新增 `scripts/demo_offline.py`、`tests/test_delivery.py`、Docker 三文件、架构及符合性文档；更新 README、研究报告、CHANGELOG、版本与打包白名单。不删除现有可用功能。

依次核验：定向回归 → 全量 Python/前端/Ruff → 无密钥固定流程（改变输入结果同步改变）→ 实际 HTTP 启动、页面/health/API/失败导出 → Docker 构建与启动 → 白名单 ZIP 与独立目录锁定安装。真实模型请求与历史记录分别报告，不拿离线模拟替代实际调用。最终结果和每项修复状态记录在 `CONTRACT_COMPLIANCE.md` 与本版 checks.json。

保留的 P2/P3 范围：自然语言参数来源/回答全部数字的语义校验、检索准确率基准、Windows 和生产多用户部署。当前无恢复执行需求，不增加通用工作流编辑器、数据库、队列或多 Agent。

## 最终实施状态

上述七类运行问题均已修复，并新增实际 SDK、Agent、API 与前端回归。交付复核另发现并修复了白名单根目录链接越界打包、离线演示非法参数遗留 running 两项问题；全部有回归。最终验证数字和环境见 [checks.json](validation/v0.3.1/checks.json)，最终交付与剩余边界见 [DELIVERY_REPORT.md](DELIVERY_REPORT.md)。


## 续接复验与最终收尾

当前独立分支 `codex/delivery-hardening` 从 `699f61b` 接续，并保留主目录已有的 0.3.1 未提交完善成果；没有改写主目录。重新核验源码和原有 233 项离线回归后，另确认并修复以下边界：

| 问题 | 位置与影响 | 修复与回归 |
| --- | --- | --- |
| [P2] 合法混合流量被拒 | `execution.py` 要求热负荷只引用直接换算步骤，无法使用后续混合结果 | 接受已成功、已声明依赖且已核对质量流量单位的引用；13 项回归覆盖换算→混合→加热、单位、缺单位、未声明依赖及重抄拒绝 |
| [P2] 非法模型端点延迟失败 | `config.py` 只检查协议，允许缺主机或非法端口 | 配置加载时拒绝空主机、空白主机、空/越界端口及坏 IPv6；保留合法 HTTPS 与本地 HTTP |
| [P2] 尚未开始任务被标 live | `ui.py` 启动失败仍采用默认模式 | 新建记录使用 `not_started`，保留已有运行的模式和请求；配置/API 合计新增 15 项回归 |
| [P2] 构建上下文过宽 | `.dockerignore` 的目录放行继承后代，允许无关资料附件及嵌套 `.git`/缓存/build 内容 | 只放行递归 MD/TXT（兼容大小写），补充私有目录排除；使用无网络 scratch 实际构建验证，Docker 不可用时跳过 |
| [P2] 摘要直接出处不随包 | `CONTRACT_SCOPE.md` 引用根目录初步方案，但 ZIP 白名单未包含该文件 | 原方案加入白名单，摘要使用可点击相对链接，归档回归核对实际包含 |
| [P2] 复装证据未收尾 | checks.json 仍写 228 项及最后五项待重跑 | 从交付 ZIP 新建虚拟环境执行最终全量测试，记录实际数量；明确历史浏览器/模型证据的版本 |

Docker 的资料遗漏初步判断已撤回：实际基线构建证明原规则已经放行递归 TXT 和大写卡；本次修复是收紧上下文，而非恢复原本存在的功能。官方 smolagents 1.26.0 API、LightRAG 1.5.7 接入示例与 uv Docker 指南再次核对后，继续复用当前技术栈，没有新增框架或运行依赖。

最终代码已通过 262 项 Python 离线回归、20 项前端状态测试及 Ruff/JavaScript/空白检查。实际 HTTP、非 root 容器及固定数值演示均通过。原合同扫描件仍未取得，本轮使用随包摘要核对工程能力。此前密钥路径因项目搬迁而失效；2026-10-07 修正本机配置后，真实单位换算通过，4次DeepSeek请求全部成功。完整8案例和LightRAG质量复验未重跑，历史结果不计作本轮重跑。详细复装记录见 checks.json。
