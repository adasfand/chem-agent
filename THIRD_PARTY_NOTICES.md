# 第三方组件与资料说明

本工程使用下列开源组件。第三方组件的版权和许可归各自权利人所有；Python 版本及来源见 `uv.lock`，前端版本及来源见 `src/chem_agent/web/package-lock.json`。主交付包包含源码与编译页面，不捆绑第三方环境目录；可选前端依赖归档单独包含 `node_modules` 及其上游许可证文件。

| 组件 | 用途 | 上游许可与来源 |
|---|---|---|
| smolagents | 模型驱动的工具调用循环 | Apache-2.0，https://github.com/huggingface/smolagents |
| FastAPI / Starlette | 本机 HTTP 接口 | MIT / BSD-3-Clause，https://github.com/fastapi/fastapi 与 https://github.com/Kludex/starlette |
| uvicorn | ASGI 本地服务 | BSD-3-Clause，https://github.com/encode/uvicorn |
| scikit-learn | 字符 TF-IDF 文本检索 | BSD-3-Clause，https://github.com/scikit-learn/scikit-learn |
| Pint | 单位及量纲处理 | BSD-3-Clause，https://github.com/hgrecco/pint |
| Pydantic | 计划结构校验 | MIT，https://github.com/pydantic/pydantic |
| OpenAI Python SDK | 兼容接口传输（连接 DeepSeek） | Apache-2.0，https://github.com/openai/openai-python |
| python-dotenv | 本地配置加载 | BSD-3-Clause，https://github.com/theskumar/python-dotenv |
| pytest / Ruff / uv | 测试、格式检查及环境管理 | MIT / MIT / MIT或Apache-2.0；见各项目随包许可 |
| Vue 3 | 组件化前端与响应式状态 | MIT，https://github.com/vuejs/core |
| Vite / Vitest | 前端开发、打包和测试 | MIT，https://github.com/vitejs/vite 与 https://github.com/vitest-dev/vitest |
| TypeScript | 前端静态类型检查 | Apache-2.0，https://github.com/microsoft/TypeScript |
| Lucide（@lucide/vue） | 随前端打包的 SVG 图标 | ISC；部分 Feather 来源图标为 MIT，https://github.com/lucide-icons/lucide |
| ESLint 及 Vue / TypeScript 插件 | 前端代码规范检查 | 各组件许可见 npm 包内 LICENSE 与锁文件 |
| Prettier | 前端源码格式化 | MIT，https://github.com/prettier/prettier |

Node 使用开发者本机安装，不包含在交付包中。前端编译产物不依赖远程 CDN、在线字体或图标服务；保留构建工具输出的许可声明。离线开发依赖包仅供相同操作系统、CPU 架构与兼容 Node 版本使用，不能视为跨平台通用环境。依赖表列出直接使用的主要组件，传递依赖与完整许可文本以锁文件和各安装包为准。

`data/knowledge/` 内的 15 张知识卡为本项目自编教学说明，非实测物性数据库。算例比热来自示例题目，未从 NIST、PubChem 等网站抓取物性。DeepSeek 是外部模型服务，运行方须自行提供有效账户与凭据；模型服务不随源码交付。

本项目新增部分包括知识卡组织、检索策略、领域计算、执行计划校验、带单位的结果引用解析、运行证据记录、界面和验证脚本。使用框架不代表框架自动保证这些业务规则。

## 编译前端所含组件的许可原文

以下文本取自已锁定的本机 npm 包，随源码及编译页面交付。

### Vue 3

```text
The MIT License (MIT)

Copyright (c) 2018-present, Yuxi (Evan) You

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

### Lucide / Feather

```text
ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

---

The following Lucide icons are derived from the Feather project:

airplay, alert-circle, alert-octagon, alert-triangle, aperture, arrow-down-circle, arrow-down-left, arrow-down-right, arrow-down, arrow-left-circle, arrow-left, arrow-right-circle, arrow-right, arrow-up-circle, arrow-up-left, arrow-up-right, arrow-up, at-sign, calendar, cast, check, chevron-down, chevron-left, chevron-right, chevron-up, chevrons-down, chevrons-left, chevrons-right, chevrons-up, circle, clipboard, clock, code, columns, command, compass, corner-down-left, corner-down-right, corner-left-down, corner-left-up, corner-right-down, corner-right-up, corner-up-left, corner-up-right, crosshair, database, divide-circle, divide-square, dollar-sign, download, external-link, feather, frown, hash, headphones, help-circle, info, italic, key, layout, life-buoy, link-2, link, loader, lock, log-in, log-out, maximize, meh, minimize, minimize-2, minus-circle, minus-square, minus, monitor, moon, more-horizontal, more-vertical, move, music, navigation-2, navigation, octagon, pause-circle, percent, plus-circle, plus-square, plus, power, radio, rss, search, server, share, shopping-bag, sidebar, smartphone, smile, square, table-2, tablet, target, terminal, trash-2, trash, triangle, tv, type, upload, x-circle, x-octagon, x-square, x, zoom-in, zoom-out

The MIT License (MIT) (for the icons listed above)

Copyright (c) 2013-present Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
