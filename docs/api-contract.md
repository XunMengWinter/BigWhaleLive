# API 与事件协议

更新日期：2026-11-09。协议版本：1。阶段1A/1B、B站访客互动、正式推流及二创玩梗素材库检索已实现；官方open_live实连仍待应用授权，不与访客结果混同。

开发默认基址为 `http://127.0.0.1:8765`，WebSocket为同源`/ws`；当前正式服务为`http://127.0.0.1:8766`，同源边界随端口独立计算。接口仅供本地控制台与舞台使用，输入上限和模式见 [运行配置](runtime-config.md)。所有ID为字符串，时间为UTC ISO 8601；状态计算使用服务端单调时钟。

## 1. HTTP 路由

| 方法与路径 | 成功响应 | 行为 |
| --- | --- | --- |
| GET / | 200 HTML | 舞台，不隐式启动 Agent |
| GET /control | 200 HTML | 控制台，不申请播放权 |
| GET /api/health | 200 JSON | 返回 status=ok、instance_id、protocol_version=1；只表示进程存活 |
| GET /api/state | 200 JSON | 返回下文定义的完整公共状态 |
| POST /api/danmaku | 202 JSON | 接受模拟弹幕，不表示已经回复 |
| POST /api/control | 200 JSON | 执行 start、resume、pause 或 skip，返回更新后的公共状态 |
| GET /audio/{utterance_id}.mp3 | 200 audio/mpeg | 仅提供存在且未过期的生成音频；其他情况 404 |
| GET /static/、/models/、/vendor/ 下的文件 | 200 对应类型 | 只挂载明确资源目录，不提供仓库根目录 |

状态修改请求要求 `Content-Type: application/json`，否则 415；超出 16 KiB 返回 413；结构或字段不合格返回 422。所有请求对象拒绝未声明字段。存在的 Origin 不匹配本机服务时返回 403，不启用通配 CORS。

舞台查询参数：`view=obs` 切换纯采集画面；仅该视图下的显式 `audio=auto` 请求前端尝试声音解锁并按原合同申请播放权。默认仍手动启用；解锁失败显示操作入口，不自动重试或开始 Agent，不抢占已有播放者。独立本地采集服务使用 8766，所有同源与 WebSocket 边界随该端口独立计算。

### 模拟弹幕

请求：

```json
{
  "user": "小明",
  "text": "你今天怎么又在摸鱼？",
  "client_message_id": "d4dbe836-1de6-4cb0-adc8-e2f735fa26af"
}
```

`user`、`text` 必填，清洗后分别为 1–32 和 1–200 字符。`client_message_id` 为可选 UUID；控制台生成并保留该值，用于同一次发送重试。缺省时后端生成 ID，不能保证无 ID 重试的幂等性。

成功响应：

```json
{
  "event_id": "d4dbe836-1de6-4cb0-adc8-e2f735fa26af",
  "accepted": true,
  "duplicate": false,
  "queue_size": 1
}
```

同 ID 同内容重复请求返回 200，`accepted=true`、`duplicate=true`，不再次入队或调用模型。复用 ID 但内容不同返回 409 `id_conflict`。首次请求在 paused 模式返回 409 `agent_paused`；running 但无播放者时可以入队，仍受 TTL 限制。已接受 ID 的重试优先返回去重结果，即使当前已暂停；`accepted` 表示历史接受，不保证仍在队列。

用户冷却返回 429 `user_cooldown`，队列满返回 429 `queue_full`，输入命中阻止词返回 422 `content_blocked`。错误不占去重记录和用户冷却。事件收到时间及优先级均由后端赋值，客户端不能设置。

### 操作者控制

```json
{
  "action": "pause"
}
```

`start` 和 `resume` 都幂等进入 running；不抢占播放者，不重放旧发言。`pause` 取消当前任务并清空队列，返回时逻辑状态已更新，已连接舞台接收取消事件后停止声音。`skip` 只取消当前发言并保留队列，无当前发言时返回 409 `no_active_utterance`。

open_live 模式下，start/resume 还允许在平台失败且前一轮结束后启动新的有界连接尝试，不重复创建仍在运行的连接任务。HTTP返回不等待平台鉴权完成，连接结果以后续有序WS快照为准；前端不使用可能迟到的HTTP响应覆盖WS的新状态。暂停只停止主播生成与入队，平台会话和心跳保持。

### 统一 HTTP 错误

```json
{
  "error": {
    "code": "queue_full",
    "message": "等待队列已满，请稍后重试",
    "request_id": "a04ca9f2-7fa8-4f6b-a75d-882d9aee092d"
  }
}
```

验证错误也转换为此结构，不把原始请求、供应商响应或凭证回显到错误消息。

## 2. 公共状态

`GET /api/state` 与 `state.snapshot.data.state` 使用同一结构：

```json
{
  "instance_id": "4aa23b47-d63a-4bbd-b50b-14abf8575ac8",
  "ai_name": "大肥鱼",
  "epoch": 0,
  "mode": "paused",
  "phase": "idle",
  "blocked_reason": null,
  "queue_size": 0,
  "playback_owner_id": null,
  "renderer_status": "waiting",
  "llm_mode": "demo",
  "tts_mode": "off",
  "tts_status": "disabled",
  "bili_status": "disabled",
  "bili_mode": "off",
  "bili_room_id": null,
  "current": null,
  "last_error": null,
  "counters": {
    "accepted": 0,
    "duplicate": 0,
    "expired": 0,
    "rejected": 0,
    "failed": 0,
    "completed": 0
  },
  "llm_model": "",
  "tts_voice": "",
  "diagnostics": {
    "llm": null,
    "tts": null,
    "bilibili": null,
    "knowledge": {"status": "ready", "revision": "54d464a2a5db709a", "entry_count": 103, "source_count": 2, "error_code": null, "last_retrieved_ids": []},
    "companion": {"activity":"slacking","label":"摸鱼","remaining_turns":0},
    "recent": []
  },
  "tts_rate": "",
  "tts_pitch": ""
}
```

- `tts_mode` 为 off / edge / qwen_local；本地模式的 `tts_voice` 固定返回 xiaojing-v1，不返回本地解释器、模型或参考音频路径。
- `tts_rate`、`tts_pitch` 为 Edge 的公开语速/音高配置，非 edge 模式为空。
- `ai_name` 为公开主播昵称；`llm_model` 和 `tts_voice` 为公开模型/音色标识，关闭对应模式时为空，不返回密钥或服务基址。
- `mode`、`phase` 和 `blocked_reason` 的枚举见架构。paused 时 `blocked_reason=null`；running 且无 owner 时，有舞台声音受阻则为 audio_blocked，否则 no_renderer；有 owner 时仅在模型失败退避期间为 provider_backoff，其他情况为 null。旁观舞台的声音状态不能阻塞有效 owner。
- `renderer_status` 为 waiting / ready / blocked；存在播放者时为 ready，无播放者且有舞台报告声音阻塞时为 blocked，否则 waiting。
- `tts_status` 为 disabled / idle / ok / error；off 对应 disabled，edge 和 qwen_local 在首次合成前为 idle。`bili_status` 为 disabled / connecting / connected / error。
- `bili_mode`为off / open_live / web；bili_room_id为官方start或网页JSON确认的正整数房间号或null。web按用户要求只使用访客连接，不登录账号。连接失败时可能保留已验证房间号，不能据此推定仍连接；只有WS鉴权成功才返回connected。
- `current` 为 null 或 `{utterance_id, kind, text, emotion, action}`，`kind` 为 reply / autonomous。生成尚未得到台词时 text 为 null，emotion=neutral、action=none。状态不包含音频执行指令。
- `last_error` 为 null 或 `{code, message, at}`；不包含原始异常或配置值，下一次成功完成发言后清除。
- 每个首次输入拒绝增加 rejected，重复请求仅增加 duplicate；TTL 丢弃增加 expired，生成失败、TTS 失败、播放错误或超时每次增加 failed，成功收到 ended 增加 completed。TTS 失败后字幕完成可以同时增加 failed 与 completed。
- `diagnostics.llm` / `tts` 为 null 或 `{attempts, successes, failures, cancelled, last_ms, last_http_status}`。它们统计应用层适配器调用，successes 不代替台词校验或播放完成；last_http_status 仅在 LLM HTTP 适配可见，TTS 为 null。
- `diagnostics.bilibili`为null或包含received、accepted、duplicate、dropped、invalid、expired、reconnects、app_heartbeats、socket_heartbeats、socket_replies、end_failures、reason、error_code的对象；web另有authenticated（始终false）、live_status、anonymous计数。web没有应用HTTP心跳，app_heartbeats=0不是失败。数字为进程累计值，reason为安全短码，error_code为整数或null。accepted不等于已回复，socket_replies也不等于弹幕。匿名身份无法区分时，使用明确的房间匿名限流组，不伪造真实UID。不会返回登录Cookie、临时连接Token、buvid、game_id、auth_body、WSS地址、open_id或完整原始消息。
- `diagnostics.recent` 最多 20 项，字段为 utterance_id、kind、llm_ms、tts_ms、ready_ms、started_ms、result。result 随阶段推进，最终为 completed、completed_without_audio、cancelled 或错误码；失败前未发生的耗时为 null。
- `diagnostics.knowledge` 为 null（演示、替身或无知识模块）或 `{status, revision, entry_count, source_count, error_code, last_retrieved_ids}`。当前素材库全部为网友二创虚构梗（`fiction` 来源、`fictional` 条目），诊断不返回问题原文、条目正文、本机路径或来源URL；`last_retrieved_ids` 只含最多6个条目ID。status 为 ready / stale / unavailable，error_code 为 knowledge_missing / knowledge_invalid / null。
- `diagnostics.companion`包含activity（slacking/working/eating）、label（摸鱼/假装忙/干饭）和remaining_turns（0–3）。仅由后端固定触发规则和合法播放确认推进；模型输出或HTTP输入不能指定。生成尚未播放时不提交，取消时重置；无观众身份或原文。原播放事件及text/emotion/action输出合同不变。
- ready_ms、started_ms 对弹幕从后端接收事件起算，包含排队；自主发言从开始调度起算。llm_ms、tts_ms 分别记录对应步骤。诊断不包含台词、观众信息或凭证。
- 计数、诊断、短期记忆与队列仅在内存中，重启清零；不承诺持久化。

## 3. WebSocket 生命周期

服务端为每个连接分配 `connection_id`，立即发送快照。客户端必须在 5 秒内完成 hello；阶段 1A 的舞台可随后立即就绪，edge 舞台等待启用声音。FastAPI 可双向处理 WebSocket 和断连，参见[官方 WebSocket 文档](https://fastapi.tiangolo.com/advanced/websockets/)。

服务端消息统一封装：

```json
{
  "v": 1,
  "type": "state.snapshot",
  "instance_id": "4aa23b47-d63a-4bbd-b50b-14abf8575ac8",
  "epoch": 0,
  "seq": 1,
  "data": {
    "connection_id": "stage-connection-1",
    "state": {
      "instance_id": "4aa23b47-d63a-4bbd-b50b-14abf8575ac8",
      "ai_name": "大肥鱼",
      "epoch": 0,
      "mode": "paused",
      "phase": "idle",
      "blocked_reason": null,
      "queue_size": 0,
      "playback_owner_id": null,
      "renderer_status": "waiting",
      "llm_mode": "demo",
      "tts_mode": "off",
      "tts_status": "disabled",
      "bili_status": "disabled",
      "bili_mode": "off",
      "bili_room_id": null,
      "current": null,
      "last_error": null,
      "counters": {
        "accepted": 0,
        "duplicate": 0,
        "expired": 0,
        "rejected": 0,
        "failed": 0,
        "completed": 0
      },
      "llm_model": "",
      "tts_voice": "",
      "diagnostics": {
        "llm": null,
        "tts": null,
        "bilibili": null,
        "knowledge": {"status": "ready", "revision": "54d464a2a5db709a", "entry_count": 103, "source_count": 2, "error_code": null, "last_retrieved_ids": []},
        "companion": {"activity":"slacking","label":"摸鱼","remaining_turns":0},
        "recent": []
      },
      "tts_rate": "",
      "tts_pitch": ""
    }
  }
}
```

`seq` 在一个 instance 内全局递增，可以有间隙，不要求客户端看到所有序号。状态变化后向所有连接发送各自的快照，不发送历史重放。客户端忽略同实例旧序号；更高 epoch 先清除本地旧播放，再处理消息。重连后的首个快照重新建立序号基线；instance 改变时清空全部旧状态。

客户端消息统一为 `{v, type, data}`，不发送服务端 seq。下面 hello 不申请播放权：

```json
{
  "v": 1,
  "type": "client.hello",
  "data": {"role": "stage"}
}
```

role 只能为 stage 或 control，连接内不能变更。舞台准备好后发送：

```json
{
  "v": 1,
  "type": "renderer.ready",
  "data": {
    "ready": true,
    "claim_playback": true,
    "audio_status": "off",
    "character_mode": "demo"
  }
}
```

`audio_status` 为 off / ready / blocked / error，`character_mode` 为 demo / live2d。edge 模式仅 audio_status=ready 可申请；off 模式仅 off 可申请。`ready=false` 释放本连接持有的播放权；声音被阻止时用 blocked。先到的合格申请获得播放权，后到申请保持预览；服务端快照中 owner ID 是权威结果。控制台不得发送此消息。

### 服务端事件

下表 data 对象使用上述公共封装。当前发言准备完成后，先将状态更新为 awaiting_playback，再向当前播放者发送 ready，并广播快照。

| type | data 字段 | 接收方与行为 |
| --- | --- | --- |
| state.snapshot | connection_id、state | 所有连接；仅同步显示，不据此启动音频 |
| utterance.ready | 见下方示例 | 仅播放者；验证后开始音频或字幕计时 |
| utterance.cancel | utterance_id、reason | 所有连接；立即停止对应声音、计时器与动作；epoch 已递增 |
| system.error | code、message、utterance_id（可为 null） | 所有连接；显示短错误，不当作发言 |
| danmaku.received | event_id、source、user、text | 已接受的平台输入；source固定为bilibili。控制台与舞台电脑以纯文本显示，不驱动播放确认，不重放历史；电脑仅显示最近3条，断连/实例变更时清空 |
| protocol.error | code、message | 当前连接；字段或消息顺序错误 |
| server.ping | token | 所有连接；用于应用层存活检测 |

ready 的 data 示例（字幕模式）：

```json
{
  "utterance_id": "e4bfed15-c3eb-4991-a187-de6a2c4521c7",
  "kind": "reply",
  "text": "我是在认真研究怎么提高效率呢！",
  "emotion": "happy",
  "action": "nod",
  "audio_url": null,
  "display_duration_ms": 2000,
  "tts_status": "disabled"
}
```

成功语音的 audio_url 为 `/audio/{utterance_id}.mp3`，display_duration_ms 为 null，tts_status=ok；TTS 失败为 null 音频、按规则计算字幕时长、tts_status=error，并另发 system.error。

### 客户端播放确认与心跳

```json
{
  "v": 1,
  "type": "playback.started",
  "data": {
    "instance_id": "4aa23b47-d63a-4bbd-b50b-14abf8575ac8",
    "epoch": 0,
    "utterance_id": "e4bfed15-c3eb-4991-a187-de6a2c4521c7"
  }
}
```

音频在实际 playing 事件后发送 started，在 ended 后发送 `playback.ended`，后者 data 相同。字幕模式在实际显示时发送 started，计时结束发送 ended。不能在音频尚未播放时提前确认。

`playback.error` 使用相同关联字段，额外包含 `code`，取 autoplay_blocked / audio_error。服务端取消本条并将该播放者标为未就绪，直到舞台再次明确就绪。只有当前 owner、instance、epoch、utterance 匹配且阶段正确的确认生效；旧确认、重复确认和其他连接确认均忽略，不重复计数或关闭连接。

`client.pong` 的 data 为 `{token}`，匹配最近 10 秒内本连接发出的任一未确认 ping；服务端以最后一次合法 pong 判断存活，不能因下一个 ping 发出而提前作废上一 token。心跳丢失时关闭连接、释放播放权并取消当前发言。客户端若连续 10 秒未收到 server.ping，也停止本地播放、关闭连接并进入重连。

服务端向每个连接使用有界发送队列（最多 100 个事件），发送阻塞超过 2 秒或队列满则关闭该慢连接；关闭播放者按相同失效流程处理，不能让它拖住全部客户端。

首版不提供 WebSocket 控制命令，操作者统一使用 HTTP。消息不是 JSON、字段不合格或未知 type 时发 protocol.error；协议版本不符关闭 1002，角色越权关闭 1008，超限关闭 1009，未及时握手关闭 1008。

## 4. LLM 返回合同

后端向配置的兼容接口发送非流式 `model`、`messages`、`max_tokens=256`，通用服务不要求供应商特有 response_format；DeepSeek 官方域名按已核对的官方合同附加 thinking=disabled 与 response_format=json_object。system 消息来自人设与输出规则，观众文本仅作为 user 内容传入；历史只采用已完成回合。前端不直接请求模型。

读取 `choices[0].message.content`，仅接受 JSON 对象；可剥离完整包裹该对象的一层 Markdown 代码围栏，不从任意长文提取片段。演示模式输出同样的结构：

```json
{
  "text": "今天想和大家聊聊工作间隙的小乐趣。",
  "emotion": "happy",
  "action": "nod"
}
```

text 必须清洗后为 1–120 字符并通过输出检查，缺失或超长使本轮失败。emotion 允许 neutral / happy / shy / sad，action 允许 none / nod / shake_head；未知值分别回退 neutral 和 none。其他返回字段忽略，不接受模型指定的优先级、URL、工具调用或文件路径。kind、ID 和调度优先级由后端赋值。

## 5. 运行错误码

运行错误通过 system.error 与 last_error 展示，不混同 HTTP 接口错误：`llm_timeout`、`llm_unavailable`、`llm_invalid_output`、`content_blocked`、`tts_timeout`、`tts_unavailable`、`playback_timeout`、`autoplay_blocked`、`audio_error`、`renderer_disconnected`、`bili_unavailable`。具体供应商错误映射到这些稳定码，原始响应不下发。

## 背景音乐的前端边界

不新增HTTP/WS字段、控制命令或后端状态。`state.snapshot` 的 mode/owner只决定本地背景音乐资格；主播语音仍只能由 `utterance.ready` 开始，不能凭快照重放。音乐使用同源 `/static/assets/music/dream-culture.mp3`，不属于 `/audio/{utterance_id}.mp3` 的生成语音。音乐事件不发送 playback.started/ended/error、不计入对话次数、不驱动嘴型；其错误仅显示在当前舞台。实例/epoch失效、断连、暂停和释放所有权立即停止背景音乐。
