# chem-agent：化工知识增强与工具调用

开发骨架，采用 Python 3.11、smolagents ToolCallingAgent、本地字符 TF-IDF、Pint 和 Gradio。
按照两份需求 MD 的后续选型报告实施：通用 Agent 循环交给 smolagents，项目实现资料、领域工具、计划约束和真实调用记录。

**当前证据等级：源码已编写、仅静态审查。未安装项目依赖、未导入或运行本项目、未调用模型、未运行测试。**
环境文件是拟用配置，不是经过服务器验证的依赖锁。`completed` 仅表示一次程序流程完成；`acceptance_status=not_evaluated` 表示没有据此认定通过验收。

## 1. 当前内容

- 两个业务入口：`ask` 知识问答，`task` 多工具任务；均调用同一个服务层。
- 15 张自编教学知识卡，Markdown/TXT 读取、标题/段落分段、可重建 JSON 索引快照与来源追溯。
- 四个业务工具：`search_knowledge`、`convert_units`、`calc_heat_duty`、`calc_mass_balance`。
- 一个计划管理工具 `record_plan`，补充结构化步骤和依赖；它不是第五个化工业务工具。
- 显式引用解析：如 `s2.value` 由程序读取成功步骤 s2 的返回字段，覆盖模型自行填写的对应参数。
- 每次任务独立 Agent、计划和 JSONL 记录；模型收到的消息也记录，便于核对知识片段是否进入上下文。
- 命令行、Gradio 页面、三个示例、必要测试源码和验收/研究报告模板。

## 2. 目录

```text
chem-agent/
  app.py                       Gradio 页面
  cli.py                       CLI 入口
  environment.yml              服务器 Conda 环境草案
  pyproject.toml               包和候选依赖
  .env.example                 无密钥配置模板
  src/chem_agent/
    config.py                  配置与范围检查
    knowledge.py               资料、分段、TF-IDF、索引快照
    tools.py                   固定公式、Pydantic 输入、Pint 换算
    execution.py               计划管理、引用解析、状态与引用检查
    trace.py                   每次运行的 JSON/JSONL
    model.py                   模型适配和请求证据
    agent.py                   框架与领域工具装配
    service.py                 两个入口的统一业务服务
    cli.py                     CLI 子命令
  data/knowledge/              自编示例知识卡
  examples/tasks.json          三个任务与理论参考值
  tests/                      待服务器执行的测试源码
  docs/                       规划、验收矩阵、服务器说明和报告模板
```

## 3. 服务器准备（后续执行，本机无需安装）

先完成 GitHub 网页建库和协作权限，再根据实际服务器路径设置远端及上传；详见 `docs/GITHUB_UI.md`。
等代码到服务器后，在项目根目录执行以下候选命令：

```bash
conda env create -f environment.yml
conda activate chem-agent
cp .env.example .env
# 编辑 .env，填入真实模型名、服务 /v1 地址和密钥。
python cli.py build-index
python cli.py search "单相显热公式与适用条件"
python cli.py example A
python cli.py example B
python cli.py example C
python app.py
```

模型服务必须实际支持工具调用，不能仅因声称 API 兼容就认为协议已通过。服务器不需要为了本工程训练模型；使用现成 API 时检索和计算在 CPU 上执行。尚未测量运行时间或内存。
默认 UI 监听 `127.0.0.1:7860`，服务器访问方式待部署时配置 SSH 转发。若修改监听地址，应另行配置访问控制。
环境变量优先于 `.env`；CLI 默认从当前目录读取配置，也可 `python cli.py --root /path/to/chem-agent ...`。

## 4. 命令和运行证据

```bash
python cli.py ask "定压比热与热负荷有什么关系？简化计算需要哪些条件？"
python cli.py task "将1000 kg/h换算为kg/s"
python -m pytest
python -m pip freeze > requirements-server.lock.txt
```

以上均为服务器阶段命令，尚未执行。通过部署和用例检查后才保存依赖快照，并在干净 Conda 环境重新安装复核。依赖快照不自动代表跨平台锁定。

运行目录 `runs/<run_id>/`：

- `events.jsonl`：问题、配置摘要、资料哈希、计划版本、工具起止/参数/结果/错误、模型请求与响应。
- `result.json`：最终状态、答案、计划、步骤状态、输出及引用。

模型请求日志含任务和检索原文，默认不进入 Git；密钥和 API 地址会脱敏。日志不应直接当作可公开材料。
知识卡改动后索引加载会拒绝旧快照，需要重新 `build-index`。索引保存文本与元数据，TF-IDF 矩阵在加载时重建，适用于首版小语料。

## 5. 语义边界与后续工作

当前实现对 ID、依赖、数值范围、引用成员关系进行程序检查。`user:` 输入依据仍由模型声明，需人工核对是否来自题设；引用存在不代表引用支持了整句结论，最终数值与适用条件也要在服务器案例中核对。
主流程使用框架真实工具调用；没有模拟模型或预写答案兜底。检索不到资料时应解释证据不足；缺少比热等参数时应请求补充。模型对这些要求的遵循尚待实际验证。
知识卡是自编教学说明，不是工艺设计规范或实测物性库；PDF/OCR、外部数据库和模型训练未列入首版实现。
研究报告目前是待填模板，最终需写入真实记录和验证结果。完整顺序见 `docs/IMPLEMENTATION_PLAN.md`，逐项对应见 `docs/ACCEPTANCE.md`。
