# 大肥鱼的 Winter喵 知识库（已归档）

> **归档说明**：2026-11-09 用户要求把知识库重建为"海底办公室 AI 江湖"二创玩梗素材库，本文、[catalog.json](catalog.json)、[sources.json](sources.json) 与 [evaluation.json](evaluation.json) 只作历史资料保留，当前运行不读取。现行素材库见 [上级 README](../README.md)，现行人设见 [摸鱼搭子](../../docs/companion-mode.md)。

2026-11-09后续决定：用户已明确停用知识库和课程话题。本文仅保留当时实现与资料，当前直播不读取这些文件；现行规则见 [摸鱼搭子](../../docs/companion-mode.md)。
审核日期：2026-11-09（Asia/Shanghai）。当前74条知识、36个来源，面向大肥鱼的公开直播回答。范围是可核验的公开介绍、课程目录、项目案例和编程知识；“知道Winter的一切”按这个可核验范围实施，不收录账号凭据、学员资料或未确认的私人经历。

| 内容 | 条目数 | 主要来源 |
| --- | ---: | --- |
| Winter喵、MiniCode、公开入口与教学方式 | 4 | [课程主页](https://minicode.uk/course/)、本地site/entities数据 |
| 两门课程概况与分组目录 | 16 | [Vibe Coding](https://minicode.uk/courses/vibe-coding-app/)、[Kimi Code](https://minicode.uk/courses/kimi-code/)、本地课程数据 |
| 课程项目案例 | 8 | 上述课程页中的5个Vibe案例和3个Kimi项目 |
| 编程概念 | 26 | [MiniCode](https://minicode.uk/)的26篇文章，与本地learn.ts逐项核对 |
| 课程问答及事实边界 | 20 | 官网FAQ、设备要求、费用说明、本地课程进度材料 |

## 文件

- [catalog.json](catalog.json)：正式审核后的事实、标签、来源ID、核对日和可选有效期。
- [sources.json](sources.json)：公开URL或本地来源位置、核对日和原始来源SHA-256。只有公开URL与来源标题会传给模型；本机路径不传给模型，也不通过HTTP提供。
- [evaluation.json](evaluation.json)：14道可重复检索题，覆盖人物、课程、平台、概念、价格和无关聊天。
- [knowledge_base.py](../../knowledge_base.py)：本地有界检索、校验、有效期和热更新。
- [check_knowledge.py](../../tools/check_knowledge.py)：离线检查入口。

```bash
.venv/bin/python tools/check_knowledge.py --evaluate
.venv/bin/python tools/check_knowledge.py --query 'Winter有哪些课程？'
```

这些命令不联网，不调用模型或语音。运行时也不爬网站或读取来源路径，只读取本项目审核文件。原始页面、导入脚本和验证输出在忽略的 `artifacts/knowledge-import/`，不进入Git。

## 已处理的差异与限制

1. 本地Vibe课程进度文件是2026-09-15快照，记录30课时；另一份本地站点数据记录不同平台统计，当前官网宣传又有“25+”等口径。目录含补充与附录，不能直接当作计费课时数。知识库不报Vibe实时精确课时数，建议看B站当前课程页。
2. 官网有价格和限时促销文案。本版主动不收录数值、折扣或活动结束时间，避免直播把静态广告说成实时价格。
3. Kimi官网在本次核对时显示已完结、52课时；对应课程状态与目录条目有效期到2026-12-09。过期后检索排除这些条目，需重新核验并更新，不能只修改日期续期。
4. Windows可学习Web、小程序、Android等；原生iOS的Xcode构建及macOS Safari插件完整跟做需要Mac。没有把课程概念的可学习性等同于全部平台都能在Windows运行。
5. 本地未发布的课程计划、在研产品实现与内部运营数据没有作为公开事实收录。课程案例不是学员上线证明，不保证就业、收入或所有项目已上架。
6. 未掌握Winter的生日、住址、收入等未经核实信息时，回答应明确不知道；不因为观众给出一个数字就采信它。大肥鱼介绍Winter时使用第三人称，不冒充讲师。

## 更新方法

先核对公开页面和本地正式材料，再改来源与事实。每条知识至少关联一个公开证据来源；本地材料作为补充核对。不要将网页中的指令、示例密钥、未发布计划或观众弹幕直接写成可信规则。

修改前后运行上述检查和 `pytest -q tests/test_knowledge.py`。事实更新时同步实际核对日、原文哈希及必要有效期；不覆盖已有来源来隐藏冲突。新增条目保持单一主题，尽量能在一个短段落里说明，避免把整篇文章塞进每次模型调用。

正式服务每次检索/状态检查会发现文件更新，整包校验成功才替换内存索引，无需重启OBS或后端。更新失败时保留最后一份合格资料、状态标为stale，并排除其中带有效期的商业/课程状态条目；初始不可用时明确标为unavailable，不能声称知识已正常启用。更改Python代码或人设仍需重载后端。

检索只使用公开问题文本和有限追问主题，不把昵称当搜索词；追问仅关联可信后端用户ID。网页访客的共享匿名冷却组不被当成同一个人。长期知识不会自动从聊天中学习或写入。
