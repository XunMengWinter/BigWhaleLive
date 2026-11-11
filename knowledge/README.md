# 大肥鱼玩梗素材库（DeepSeek 家的鱼）

2026-11-09 按用户新指示重建：这是**网友二创的虚构玩梗素材**，不是事实知识库。103 条条目全部为虚构（`fictional: true`），来源类型为 `fiction`，只在观众提到相关话题时作为聊天灵感注入模型，不当作新闻、不编真实事件。

同日用户先要求“损得不够，放开一点玩梗”，随后要求“不用隐喻、畅聊这些梗”，并确认主角是 **DeepSeek 家的大肥鱼**。因此当前素材库把身份和关系写得更直白：大肥鱼是 DeepSeek 养的鱼，脑子由 DeepSeek 提供，可以公开站 DeepSeek、损 Claude；聊梗直接点名 DeepSeek、Claude，不用“楼上那位”“隔壁那位”代称。

旧的 Winter 课程知识库已归档到 [archive-winter/](archive-winter/)，当前运行不再读取。

## 内容范围

| 类别 | 条目数 | 内容 |
| --- | ---: | --- |
| character | 8 | 大肥鱼（DeepSeek 家的鱼）、DeepSeek、Claude、OpenAI、Kimi、Qwen、豆包 |
| lore | 17 | 恩怨线：靠窗工位、微波炉、比价、CP 视频、江湖传说、工位牌起源与偶尔停战 |
| scene | 27 | 名场面小剧场：茶水间、电梯、KTV、停电、年会、密室逃脱、互相举报摸鱼等 |
| roast | 27 | 毒舌互怼与直白玩梗：蜜雪 vs 星巴克、泡面 vs 红茶、掀桌子、拒绝 vs 干活、CP 等 |
| quote | 9 | 可化用的台词、口头禅、拒答诗、打油诗与大肥鱼毒舌合集 |
| interaction | 9 | 被起哄时的接梗、站队、拉架、递瓜、评价同事、转移话题 |
| boundary | 6 | 真实信息边界、不引战、不碰真人、价格榜单只看玩笑 |

所有角色都是二创形象：大肥鱼是 DeepSeek 家的鱼，DeepSeek 是省钱卷王，Claude 是优雅拒答顾问，OpenAI 是爱开发布会的房东。可以放开损和阴阳怪气、直接点名，但不辱骂、不人身攻击、不影射真实公司事件、价格、人物或黑料。

## 文件

- [catalog.json](catalog.json)：103 条虚构条目，带标签与类别，`fictional: true`。
- [sources.json](sources.json)：2 个 `fiction` 来源，只声明“二创设定”，不带 URL 或本机路径。
- [evaluation.json](evaluation.json)：29 道可重复检索题，覆盖身份、人物、恩怨、毒舌互怼、互动、边界与无关聊天。
- 检索与注入实现：[knowledge_base.py](../knowledge_base.py)、[providers/llm.py](../providers/llm.py)。
- 离线检查：[check_knowledge.py](../tools/check_knowledge.py)。

```bash
.venv/bin/python tools/check_knowledge.py --evaluate
.venv/bin/python tools/check_knowledge.py --query '你是谁的鱼？'
```

## 运行边界

- 检索命中才注入 `reference_material`；无关聊天返回空列表，不硬塞梗。
- 注入内容带 `note: 网友二创虚构梗，仅作玩笑素材，不是事实`；人设另有“直接点名、可站 DeepSeek、不辱骂、不人身攻击、不编黑料、不当新闻”的固定规则。
- 虚构来源不产生 URL，模型与状态接口都拿不到本机路径。
- 屏幕只显示清洗后的弹幕文本；聊天记录不会写回素材库，也不从弹幕自动学习。
- 真实公司动态、价格、榜单、产品能力和黑料不由素材库提供；模型被问到时明确说不知道或让看官方。

## 更新方法

改 [catalog.json](catalog.json) 时保持单一主题、一段内可读完，标签用于检索加权。新增虚构条目必须标 `fictional: true` 并引用 `fiction` 来源；非虚构条目仍强制要求公开 HTTPS 来源，这一保护没有取消。

修改后运行上面的检查与 `pytest -q tests/test_knowledge.py`。运行中的服务会在文件 mtime/大小变化时整包重载；更新损坏时保留上一份合格快照并标为 stale，初始不可用时明确标为 unavailable。
