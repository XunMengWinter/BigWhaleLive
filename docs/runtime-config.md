# 运行配置与开发环境

更新日期：2026-11-09。阶段1A、1B、官方弹幕适配及用户指定的web访客读取已实现。web固定房间9748572，不等待开放平台审批，也不登录账号；真实消息/语音验收独立记录。

## 开发基线与依赖交付

使用 Python 3.11 和单 worker Uvicorn。阶段 1 的直接依赖为 FastAPI、Uvicorn（含 WebSocket 支持）、Pydantic 2、pydantic-settings、httpx 和 edge-tts；测试使用 pytest、pytest-asyncio、httpx。真实服务依赖可以安装，但默认模式不得发起网络请求。

实施者在隔离虚拟环境中选择兼容补丁版本，维护 `requirements.in` 与精确锁定的 `requirements.txt`，开发依赖同样维护 `.in` 和 `.txt`；开发锁文件包含运行依赖。锁文件生成工具作为开发依赖记录，不以全局环境的 `pip freeze` 代替项目依赖解析。阶段 2 增加 Node.js 22、`package.json`、`package-lock.json` 和本地静态构建脚本；PixiJS 6.x 与插件版本必须经过真实模型验证。

## 模式组合

| 环境 | LLM_MODE | TTS_MODE | BILI_MODE | 预期行为 |
| --- | --- | --- | --- | --- |
| 阶段 1A 离线演示 | demo | off | off | 无外部请求，预设台词与字幕，演示角色 |
| 阶段 1B 语音验证 | demo | edge | off | 预设台词加真实联网语音 |
| 阶段 1B 真实 AI | openai | edge | off | 真实 LLM 加真实语音，仍用模拟弹幕 |
| 当前固定声线 | openai | qwen_local | off | DeepSeek + 本地小鲸 v1，需 Apple Silicon 与预装模型 |
| 当前网页房间读取 | openai | qwen_local | web | 按用户要求访客读取固定房间9748572，不登录账号 |
| 阶段 3 平台联调 | openai | qwen_local | open_live | 增加已授权 B站事件接入，保留小鲸固定声线 |

上表列出常用组合，各模式可独立设置。`LLM_MODE=openai`仅指接口兼容形式，不绑定服务商。模式显式决定，不根据密钥偷偷切换。本机私有.env当前为openai/qwen_local/web，使用DeepSeek和小鲸固定声线；官方申请期间按用户指令访客读取9748572。握手成功、心跳正常、本地替身测试不等于已收到真实弹幕。

## 环境变量

加载顺序：进程环境变量 > 项目 `.env` > 默认值。未知的项目配置键应给出配置错误，避免拼写错误静默生效；不把无关系统环境变量当作错误。模式错误、范围错误或必填配置缺失时启动失败，输出键名和原因，不输出值。

| 变量 | 类型与默认值 | 校验与用途 |
| --- | --- | --- |
| LLM_MODE | demo / openai，默认 demo | openai 模式须同时提供以下三项 |
| LLM_API_KEY | 字符串，默认空 | 仅后端读取，不通过状态接口返回 |
| LLM_BASE_URL | URL，默认空 | 使用 HTTPS，或本机 HTTP；不含用户信息、查询串和片段。填写服务商给出的基址，例如 `https://api.deepseek.com` 或以 `/v1` 结尾的基址；适配器只追加 `/chat/completions` |
| LLM_MODEL | 字符串，默认空 | 本机已验证 DeepSeek 官方 `deepseek-flash`；其他模型按所用服务确认 |
| AI_NAME | 字符串，默认 大肥鱼 | 去空白后 1–32 字符，作为可替换人设默认值 |
| TTS_MODE | off / edge / qwen_local，默认 off | edge 联网；qwen_local 使用本地固定声线，两者失败均显式字幕降级，不互相切换 |
| TTS_VOICE | 字符串，默认 zh-CN-XiaoyiNeural | edge 失败显示错误，不保证音色永久可用 |
| TTS_RATE | 带正负号的百分比，默认 +8% | 仅 edge；范围 -50% 到 +50% |
| TTS_PITCH | 带正负号的 Hz，默认 +35Hz | 仅 edge；范围 -100Hz 到 +100Hz |
| TTS_LOCAL_PYTHON | 本地路径，默认 .cache/voice-env/bin/python | qwen_local 使用的独立 Python 解释器，保留虚拟环境入口路径 |
| TTS_LOCAL_MODEL | 本地目录，默认 .cache/models/xiaojing-base | 安装脚本指向固定 Base 模型快照；运行时离线，缺失时启动报错 |
| TTS_LOCAL_TIMEOUT_SECONDS | 整数，默认 90，范围 5–120 | 本地模型加载与整条合成的总时限，超时终止工作进程 |
| BILI_MODE | off / open_live / web，默认 off | open_live 须提供四项官方配置；web 不需要这些Key |
| BILI_ROOM_ID | 正int64，默认9748572 | web模式的固定房间，后端通过网页确认实际房间号 |
| BILI_APP_ID | int64 范围的十进制正整数字符串，默认空 | 后端构造平台请求时按官方字段类型转换，不是房间号 |
| BILI_ACCESS_KEY | 字符串，默认空 | 开发者凭证 |
| BILI_ACCESS_SECRET | 字符串，默认空 | 后端签名密钥 |
| BILI_AUTH_CODE | 字符串，默认空 | 主播身份码，不回传给前端 |
| LIVE2D_MODEL_URL | 同源路径，默认空 | 为空显示演示角色；非空须以 `/models/` 开头且无 `..`、查询串或外部域名 |
| AUTONOMOUS_INTERVAL_SECONDS | 整数，默认15，范围5–120；当前正式本机为8 | 上一次发言结束后最短自主等待，不含LLM/TTS耗时；弹幕不受此间隔限制 |
| QUEUE_CAPACITY | 整数，默认 100，范围 1–1000 | 只计算等待处理的弹幕，不含当前发言 |
| EVENT_TTL_SECONDS | 整数，默认 60，范围 5–300 | 从后端接收时起计算，不由客户端时间控制 |

用户已明确授权使用web房间读取，`BILI_ROOM_ID`现为有效配置。当前私有配置为web/9748572。按用户禁止登录的要求，不支持账号会话、扫码或SESSDATA配置，不读取浏览器登录Cookie。身份被隐藏的文本使用匿名房间冷却组，不伪造UID。无网络自检：`.venv/bin/python tools/check_bilibili.py`；`--listen --seconds 60`显式验证真实接收，不调用LLM/TTS。官方路线保留，说明见 [接入指南](bilibili-setup.md)。

### 阶段 1A 配置模板内容

以下内容已写入项目 `.env.example`。运行时可使用默认值，或首次复制为 `.env` 后修改：

```dotenv
LLM_MODE=demo
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
AI_NAME=大肥鱼
TTS_MODE=off
TTS_VOICE=zh-CN-XiaoyiNeural
TTS_RATE=+8%
TTS_PITCH=+35Hz
BILI_MODE=off
BILI_APP_ID=
BILI_ACCESS_KEY=
BILI_ACCESS_SECRET=
BILI_AUTH_CODE=
LIVE2D_MODEL_URL=
AUTONOMOUS_INTERVAL_SECONDS=15
QUEUE_CAPACITY=100
EVENT_TTL_SECONDS=60
```

## 首版固定参数

这些是本次实施默认值，不是外部性能承诺。集中放在配置模块，测试允许注入较小数值，不必全部暴露成环境变量。

| 参数 | 默认值与处理 |
| --- | --- |
| 昵称 / 弹幕 / 台词上限 | 分别 32 / 200 / 120 Unicode 字符；空白不算有效内容 |
| HTTP JSON / WebSocket 单帧上限 | 分别 16 KiB / 16 KiB；超限拒绝 |
| 每用户接受间隔 | 5 秒；同 ID 重复请求先走去重，不再次占冷却 |
| 去重记录 | 最长 10 分钟，最多 1000 条；超量移除最早项 |
| LLM / TTS 单次总时限 | LLM 20 秒、Edge 20 秒、本地小鲸默认 90 秒；均不自动重试 |
| LLM 输出 token 上限 | 256；文本必须再次经过长度和内容校验 |
| LLM 响应体上限 | 64 KiB，超限按无效输出结束本轮 |
| LLM 失败退避 | 5 秒，不重试该事件；延迟期间可继续入队 |
| 握手 / 播放启动 / 播放结束时限 | 分别 5 / 10 / 45 秒；结束时限从 started 计算 |
| 舞台重连 | 1、2、4、8、16、30 秒，之后每 30 秒重试；连接成功后重置 |
| 本地 WebSocket 心跳 | 服务端每 5 秒发 ping，连续 10 秒无合法 pong 则关闭并释放播放权；客户端连续 10 秒无 ping 时也停止播放并重连 |
| 字幕模式展示时长 | 字符数 × 80 毫秒，最短 2 秒、最长 10 秒 |
| 记忆上限 | 最近 20 个完成回合；每回合观众文本不超过 200、台词不超过 120 字符 |
| 音频清理 | 每 60 秒；保留不超过 1 小时、最多 200 个已结束文件，另保留当前发言；启动时清理遗留临时文件 |
| 音频大小 | 单条最多 5 MiB，超限中止并按 TTS 失败处理 |
| B站 HTTP / WS 鉴权 / 收尾 | 分别 10 / 10 / 5 秒；start 响应不确定时不盲目重复开启 |
| B站两套心跳 | 应用 HTTP 与 WS 应用层心跳分别每 20 秒；WS 超过 40 秒无心跳回复触发失败 |
| B站重连 | 当前尝试轮内按 2、4、8 秒最多重连 3 次；权限/鉴权不自动重试，结束推送等待手动重连 |
| B站响应与帧 | HTTP 响应 64 KiB；单条 WS 消息 1 MiB；递归解压总量 4 MiB、最多 512 包、最多 4 层压缩 |
| 网页模式 | 浏览器兼容HTTP请求、WBI、版本3有界Brotli；房间网页上限2MiB。WS心跳30秒，无回复60秒失败；连续失败仍按2/4/8秒最多3次重连，稳定30秒且心跳新鲜后重置连续故障预算。没有应用HTTP心跳或start/end RPC |

B站接入使用 websockets 17.4，已列为直接运行依赖；没有引入废止的 bilibili-api-python。两套心跳与重连任务在应用退出时回收；end 请求有独立的有界收尾任务，关闭期间取消连接任务也不会提前中断已经开始的 end。

## 已验证真实服务配置

真实模式使用 Chat Completions 兼容接口。对 DeepSeek 官方域名，按其[当前模型调用说明](https://api-docs.deepseek.com/)使用 `deepseek-flash`，根据[思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)显式关闭 thinking，并按[JSON 输出文档](https://api-docs.deepseek.com/guides/json_mode/)启用 JSON 对象输出。其他兼容服务不附加这些供应商参数。

Edge TTS 已验证版本为 7.3.1、音色为 zh-CN-XiaoxiaoNeural。应用层不重试；SDK 自身在 403 时有一次鉴权时间校准处理，仍受应用总时限约束。当前不接入浏览器原生朗读来替代失败的 Edge 语音。

本机密钥按用户授权从已有项目配置复用，保存在 Git 忽略的 `.env`，权限为 0600；不在文档、示例或前端保存值。没有本地配置的新环境仍默认离线。

## 已验证运行命令

本机已在全新临时环境完成安装与测试。首次创建虚拟环境使用 uv，避免本机 Python 入口符号链接导致标准 venv 找不到运行库；已有 `.venv` 时直接激活。复制配置只用于首次初始化，不覆盖已有文件。

```bash
uv --cache-dir .cache/uv venv --python 3.11 --seed .venv
source .venv/bin/activate
python -m pip install --cache-dir .cache/pip -r requirements-dev.txt
# 可选，仅首次复制
if [ ! -f .env ]; then cp .env.example .env; fi
python -m uvicorn main:app --host 127.0.0.1 --port 8765 --workers 1
```

另一个终端在同一虚拟环境中验证：

```bash
python -m pytest -q
curl http://127.0.0.1:8765/api/health
```

打开舞台 `/` 与控制台 `/control`，使舞台就绪，在控制台点击开始，再发送模拟弹幕。stage 连接不自动开始发言；edge 模式先启用声音。

## 外部资源

- 阶段 1A：不需要外部资源。
- 阶段 1B：由用户配置真实 LLM 凭证；验证 Edge TTS 网络可达性。
- 阶段 2：用户提供授权角色和相应 Core；记录准确版本、来源与使用条件。正式素材是否纳入 Git 按授权与用户要求决定，不能按“过程文件”批量忽略源素材。
- 阶段 3：开发者和应用接入资格、消息权限及身份码；联调前复核官方签名、应用会话与消息协议。
- 阶段 4：OBS 本地采集验证；正式推流需要目标直播间和用户开播授权。

## 小鲸 v1 固定声线

用户已明确认可本地原创试听，当前本机私有配置改用 `TTS_MODE=qwen_local`。该模式始终返回音色标识 `xiaojing-v1`，不使用 Edge 的 TTS_VOICE、TTS_RATE、TTS_PITCH。原晓伊设置被否定为最终音色，Edge 仅保留为显式可选适配；失败时不切换声线。

需要 Apple Silicon macOS、Metal 和 PATH 内可用的 ffmpeg。参考 WAV、文本、SHA-256、模型 revision、随机种子与采样温度固定在 `assets/voices/xiaojing-v1/`；这些是正式运行资源，其他音频和权重仍不加入 Git。更换声线须遵循用户的新指令并新增版本。

在项目根目录安装独立环境及固定模型，主应用依赖不受影响：

```bash
python tools/setup_local_voice.py
```

脚本使用 uv 和 `requirements-voice.txt`，将 MLX Audio 0.6.4 安装在 `.cache/voice-env/`，下载 manifest 指定的 Qwen3-TTS Base 4bit revision 到 `.cache/huggingface/`，并设置 `.cache/models/xiaojing-base` 符号链接。模型卡标注约 2.33 GB 权重；缓存与环境另外占空间。此安装过程需要网络，运行时启用 HF_HUB_OFFLINE，不自动补下载。

私有 `.env` 设置：

```dotenv
TTS_MODE=qwen_local
TTS_LOCAL_PYTHON=.cache/voice-env/bin/python
TTS_LOCAL_MODEL=.cache/models/xiaojing-base
TTS_LOCAL_TIMEOUT_SECONDS=90
```

重启服务并刷新舞台与控制台，点击启用声音。首次发言加载模型，后续发言复用常驻进程；暂停合成会终止该进程，下次重新加载。当前采用完整合成后播放，时限是资源边界，不是实时响应保证。运行程序的宿主须有 Metal 访问能力。

依赖升级在 Apple Silicon 环境用 uv 从 `requirements-voice.in` 解析，并重新验证：`uv pip compile --python .cache/voice-env/bin/python --output-file requirements-voice.txt requirements-voice.in`。不要把语音环境的全部依赖并入主应用环境。

## 当前 Mac 的独立 OBS 采集

`tools/obs_local.py prepare --install` 安装本项目专用的 `BigWhaleLocal` 配置/集合，拒绝覆盖无项目标记的同名配置。文件使用 OBS 要求的无空格 `key=value` 格式；画布/输出/浏览器来源均为1080×1920、30 FPS，录制使用本机 Apple H.264 硬件编码器、MKV、单条音轨，关闭桌面和麦克风设备及浏览器音频监控。

`tools/start_local_capture.command` 在8766启动独立单进程服务，读取既有 `.env` 的模型和固定声线，但默认将弹幕置为off；`--with-danmaku` 才沿用原弹幕配置。初始暂停，不自动开播。生成音频在 `runtime/obs/audio/`，录制在 `artifacts/obs-recordings/`，均被Git忽略。该服务不与8765共享播放权、内存或音频目录。

OBS来源固定 `/?view=obs&audio=auto`；显式自动解锁只尝试一次，失败保留手动启用，不绕过唯一播放者协议。完整启动、安装和恢复见 [本地采集](obs-local.md)。

正式直播另用 `BigWhaleLive` 配置/集合和 `tools/start_live.command`，固定8766并启用 `.env` 中的弹幕配置。本机已按用户授权配置web游客读取9748572，当前Agent为running。OBS视频推流4500kbps、音频160kbps，1080×1920/30FPS、Apple H.264硬件编码，自动重连间隔2秒、最多10次。私有推流配置只存在OBS用户配置和忽略的 `runtime/obs-live/`，权限0600，不作为环境模板或源代码。启动脚本本身不开始OBS推流，重新启动后的Agent仍需在控制台开始；操作与暂停见 [正式直播](live-operation.md)。

## 二创玩梗素材库

无需新增环境变量、数据库或依赖。真实LLM读取项目固定的`knowledge/sources.json`和`catalog.json`；当前103条条目、2个`fiction`来源，全部标记`fictional: true`。按当前弹幕或自主话题做BM25式本地检索，默认最多4条，`reference_material`序列化最多6000字符；只有命中才注入，无关聊天返回空参考。文件各最多2MiB、最多256条/128个来源；没有任意资源路径配置或运行时爬取。虚构来源不产生URL，模型与状态接口都拿不到本机路径。

合格素材文件可热更新，运行状态见`diagnostics.knowledge`；异常保留最后合格资料并标stale，初始不可用标unavailable。非虚构条目仍强制要求公开HTTPS来源，虚构条目必须引用`fiction`来源，防止把未核实内容伪装成事实。课程与新闻仍停用，旧Winter资料归档在`knowledge/archive-winter/`、运行不读取。人设、话题或代码变更仍需句间暂停并重载后端，OBS推流保持。维护与验证见 [素材库合同](knowledge-base.md)。

## 全面屏内容安全区

OBS输出仍为1080×1920（9:16）。舞台前景容器宽度为画布的16/19.5，即82.051282%；左右各8.974359%，实际约886.15×1920，起点x≈96.92。背景铺满画布，关键前景在该容器内，适应播放器将视频居中填满9:19.5屏幕时的左右裁切。此为视频内容安全区，与浏览器的设备env(safe-area-inset-*)不是一回事；不承诺适应所有播放器悬浮按钮或更长屏幕的任意裁切。

## 当前摸鱼搭子配置

用户明确停用课程和新闻内容；知识库随后按新指示重建为二创玩梗素材库并恢复检索，`diagnostics.knowledge`为对象，不新增启用开关或新闻轮播。角色状态只包含摸鱼/假装忙/干饭和0–3个后续回合，规则见 [摸鱼搭子](companion-mode.md)。

本机私有.env仅将AUTONOMOUS_INTERVAL_SECONDS从15改为8；其余配置逐字段核对未变，包含声线、模型、访客弹幕和房间。默认Settings仍为15秒，示例保持兼容；8秒是本机正式模式的最短自主等待，不含LLM/TTS/播放时间，不承诺每8秒说一句。

## 前端语音口型

无需新增环境变量或依赖；使用浏览器AudioContext解码同源MP3副本，原语音元素仍是唯一主播语音输出（背景音乐另用独立元素）。分析取样20ms，最多8MiB/120秒，fetch时限5秒；实际后端音频上限仍5MiB。每条发言只保留当前包络，取消/换源/退出中止fetch且用revision丢弃迟到解码结果。嘴部跟踪固定为`static/assets/dsh-pet/mouth-tracking.json`（speaking/24fps/241帧）。分析或跟踪失败在舞台外诊断显示，不中断语音、不伪称精确嘴型。

## 直播背景音乐

无新增依赖或环境变量。固定本地曲目 `static/assets/music/dream-culture.mp3`（214.36秒，70 BPM钢琴/轻打击乐，循环），正式资源与来源说明保留Git；原始下载及测试录制在忽略目录。静态资源不由TTS音频清理任务管理。

音乐由 `static/js/background-music.js` 控制：标准化至约−18 LUFS，平时音量0.28、实际人声播放时0.09；压低120ms，回升/首次淡入1400ms，暂停/断连立即归零。初始化播放最多等待8秒，失败锁存并显示重试入口。仅开启人声、running且取得唯一播放权的舞台播放；TTS off字幕演示不自动发音乐。

普通舞台有「关闭音乐/开启音乐」按钮，仅影响当前页面；OBS正常时隐藏控制，音乐失败时显示重试入口。刷新页面恢复默认开启，仍须通过运行/播放权/声音就绪检查；可在OBS来源交互中使用该控件的错误重试入口。停止全部声音用控制台暂停主播。
