# 第三方组件与资料

项目通过依赖调用第三方库，未复制其源码到工程。实际安装版本和各组件许可证需要在服务器依赖锁定后随交付清单核对。

| 组件 | 使用范围 | 官方来源 |
|---|---|---|
| smolagents（选定1.26.0） | ToolCallingAgent、Tool、OpenAIModel | https://github.com/huggingface/smolagents/tree/v1.26.0 |
| scikit-learn | 字符TF-IDF与矩阵检索 | https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html |
| Pint | 单位换算与量纲校验 | https://pint.readthedocs.io/en/stable/ |
| Pydantic | 参数Schema与校验 | https://docs.pydantic.dev/latest/ |
| python-dotenv | 环境文件读取 | https://github.com/theskumar/python-dotenv |
| Gradio | 薄层演示页面 | https://www.gradio.app/docs |
| pytest | 服务器验证用测试 | https://docs.pytest.org/ |

知识卡均标记为本工程自编教学说明，未从 PubChem/NIST 抓取物性数据；示例中的比热4.18是题目假设。
API契约参考 smolagents v1.26.0 文档及对应版本源码；尚未安装或运行框架。
项目自身的授权许可应由权利方决定，本次不代选开源许可证。
