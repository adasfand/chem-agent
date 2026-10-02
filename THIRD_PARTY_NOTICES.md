# 第三方组件与资料说明

本工程使用下列开源组件作为运行依赖。第三方组件的版权和许可归各自权利人所有；依赖版本及下载来源见 `uv.lock`。交付包提供本项目源码，不捆绑第三方环境目录。

| 组件 | 用途 | 上游许可与来源 |
|---|---|---|
| smolagents | 模型驱动的工具调用循环 | Apache-2.0，https://github.com/huggingface/smolagents |
| LightRAG | 实体关系抽取、知识图谱与向量混合检索 | MIT，https://github.com/HKUDS/LightRAG |
| FastEmbed | 本地中文文本向量化 | Apache-2.0，https://github.com/qdrant/fastembed |
| FastAPI / Starlette | 本机 HTTP 接口 | MIT / BSD-3-Clause，https://github.com/fastapi/fastapi 与 https://github.com/Kludex/starlette |
| uvicorn | ASGI 本地服务 | BSD-3-Clause，https://github.com/encode/uvicorn |
| scikit-learn | 字符 TF-IDF 文本检索 | BSD-3-Clause，https://github.com/scikit-learn/scikit-learn |
| Pint | 单位及量纲处理 | BSD-3-Clause，https://github.com/hgrecco/pint |
| Pydantic | 计划结构校验 | MIT，https://github.com/pydantic/pydantic |
| OpenAI Python SDK | 兼容接口传输（连接 DeepSeek） | Apache-2.0，https://github.com/openai/openai-python |
| python-dotenv | 本地配置加载 | BSD-3-Clause，https://github.com/theskumar/python-dotenv |
| pytest / Ruff / uv | 测试、格式检查及环境管理 | MIT / MIT / MIT或Apache-2.0；见各项目随包许可 |

`data/knowledge/` 内的前 15 张知识卡为本项目自编教学说明；其余 6 张是根据 BIPM、IUPAC、NIST 和 MIT OCW 公开原始资料独立撰写的中文概括，每张均标明原始链接和适用边界。NIST 卡片仅说明气相水热容数据的温区与使用边界，系统不将其系数当作自动物性输入。DeepSeek 是外部模型服务，运行方须自行提供有效账户与凭据；模型服务不随源码交付。

本项目新增部分包括知识卡组织、检索策略、领域计算、执行计划校验、带单位的结果引用解析、运行证据记录、界面和验证脚本。使用框架不代表框架自动保证这些业务规则。
