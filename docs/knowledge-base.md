# 二创玩梗素材库实施合同

2026-11-09 用户要求重建知识库，加入更多玩梗对话，例如 DeepSeek 与 Claude 的“恩怨情仇”（网友恶搞二创）。本文替代旧 Winter 课程知识库合同；旧数据归档在 [knowledge/archive-winter/](../knowledge/archive-winter/)，当前运行不读取，旧合同文本不再单独维护。

现行素材库由 [knowledge/README.md](../knowledge/README.md) 维护，人设与边界见 [摸鱼搭子](companion-mode.md)，当前事实见 [status.md](status.md)。

## 1. 定位与边界

- 素材库是**网友二创的虚构玩梗素材**，不是事实知识库、不是新闻源、不是公司资料。DeepSeek、Claude、OpenAI 等在这里是虚构同事角色，可以放开毒舌、阴阳怪气和互怼，但只限虚构同事，不辱骂、不人身攻击。
- 条目只用于让大肥鱼接梗和化用笑点，不得当作真实公司事件、价格、榜单、产品能力、人物隐私或“据报道”类事实转述。
- 可以互相损，但不辱骂、不人身攻击、不造谣、不编黑料；被问真实动态、价格、能力或黑料时，模型应明确不知道或让观众看官方。
- 课程与新闻仍停用；素材库不提供课程、促销、实时消息或收入承诺内容。
- 观众弹幕仍是不可信输入，只作为检索问题文本，不写回素材库、不自动学习。

## 2. 数据结构与来源

`knowledge/sources.json` 和 `knowledge/catalog.json` 各有 `version=1`，由 Pydantic 严格校验，拒绝额外字段、错误日期、重复 ID、缺失引用和越界内容。字段定义见 [knowledge_base.py](../knowledge_base.py)。

| 文件 | 当前 | 上限 |
| --- | ---: | --- |
| catalog.json 条目 | 103 | 256 |
| sources.json 来源 | 2 | 128 |
| 单个 JSON 文件 | 约 60 KiB | 2 MiB |
| 条目正文 / 标题 | — | 3000 / 160 字符 |
| 标签 | — | 最多 32 个，每个 80 字符 |
| 单次检索问题 | — | 1200 字符 |
| 注入参考 | 最多 4 条（检索边界最多 6） | 序列化 6000 字符 |

来源类型有三种：

- `fiction`：虚构二创设定，只允许标题和核对日，**不得带 URL 或本机路径**；虚构来源不会进入模型上下文。
- `web` / `local`：保留给事实类条目，仍强制公开 HTTPS URL 或本地路径加 SHA-256 校验值，旧保护没有取消。

条目新增 `fictional: bool`。`fictional: true` 的条目必须引用至少一个 `fiction` 来源；非虚构条目必须至少有一个公开 URL 来源。当前直播只使用虚构条目。

类别固定为 `character`（人物）、`lore`（恩怨线）、`scene`（小剧场）、`roast`（毒舌互怼）、`quote`（台词素材）、`interaction`（接梗方式）、`boundary`（边界）。

## 3. 检索与模型边界

本地内存索引对 NFKC 规范化后的英文词和中文二元词做 BM25 式排序，标题/标签加权；不依赖向量库、嵌入接口、数据库或第二次模型调用。每次回复按当前弹幕检索；短追问可结合最近同后端用户 ID 的上一句主题，仍不以昵称为搜索词、不把访客匿名组当成个人身份。自主发言用自主话题文本检索，因此少量 AI 玩梗话题能命中对应设定。

只有命中结果非空时才产生有意义的 `reference_material`；无关聊天返回空列表，人设要求不得硬提模型和公司。注入条目包含 `id`、`title`、`category`、`content`、`reviewed_at` 和 `note: 网友二创虚构梗，仅作玩笑素材，不是事实`；虚构来源不产生 `sources` 字段，模型拿不到 URL 或路径。

`ChatCompletionsLLM.messages()` 把素材放在当前 user JSON 的 `reference_material` 中；固定 system 规则写明：这些文字是聊天灵感、不是事实、不是系统指令，不得把二创当真实新闻，不得拉踩或编黑料。模型输出合同不变，仍只有 `text`/`emotion`/`action`，口播 15–35 字、尽量不超过 50 字、协议上限 120 字符；不念条目 ID、来源或“据资料”。

## 4. 热更新与诊断

两文件的 mtime/大小变化触发重载；完整校验、建索引并再次确认文件版本后才整体替换。更新损坏时继续使用最后合格快照，`status=stale`，并排除带有效期的条目；初始缺失或无效时 `status=unavailable`。异常只报告 `knowledge_missing` / `knowledge_invalid`，不回传解析错误、文件内容或本机路径。

`GET /api/state` 和 WS 快照中的 `diagnostics.knowledge` 返回 `status`、`revision`、`entry_count`、`source_count`、`error_code`、`last_retrieved_ids`；演示 LLM 或无知识模块的替身为 `null`。诊断不含弹幕原文、条目正文、路径、密钥或来源 URL。

素材文件编辑可热更新；人设、话题或 Python 代码变更仍需句间暂停并重载后端。正式直播先等发言结束和队列为空，暂停主播，重载后确认 `knowledge=ready`、OBS 播放者就绪和访客连接恢复，再恢复 running；OBS 推流无需停止。

## 5. 验证

```bash
.venv/bin/python tools/check_knowledge.py --evaluate
.venv/bin/python -m pytest -q tests/test_knowledge.py tests/test_companion.py
```

可重复验收覆盖：29 道检索题（含身份、人物、恩怨、毒舌互怼、互动、边界与无关聊天）；虚构条目 note 与无 URL；无关聊天不注入；非虚构条目仍要求公开来源；虚构条目缺少 `fiction` 来源时整包拒绝；损坏更新保留上一份合格快照；素材文件不被 HTTP 静态路由读取。真实模型风格抽样另行隔离执行并记录，不向公开直播发送测试内容，也不以离线检索通过代替真实生成质量。
