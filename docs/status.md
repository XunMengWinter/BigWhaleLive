# 项目当前状态

更新日期：2026-11-11（Asia/Shanghai）。各阶段原始结论和样本已归档至 [验证历史](validation-history.md)。下方直播运行记录为2026-11-09的验证快照，不代表这份分享副本正在运行。

## Git基础配置（2026-11-11）

- 分享副本已初始化本地Git仓库，默认分支为 `main`；尚未暂存、提交或配置远程仓库。
- 补齐 `.gitignore` 的私钥/证书、secrets目录、模型权重和本机工具配置规则；新增 `.gitattributes` 统一文本与启动脚本的LF换行，媒体作为二进制处理；新增 `.editorconfig` 统一基础编辑格式并保留Markdown行尾换行语法。
- 验证：20项敏感/临时路径被忽略，13项正式文件可纳入版本管理；README截图、固定参考音频、角色动画与背景音乐保留。当前两个 `.DS_Store` 均被忽略，暂存区和远程配置为空。本轮不涉及应用功能验证。

## 分享版本命名（2026-11-11）

- 项目名称统一为 `BigWhaleLive`，已更新README、协作指南、B站申请名称、后端应用标题、舞台与控制台品牌/页面标题/无障碍标签，以及本地采集标记的说明文字。目录由用户自行重命名。
- OBS本地测试配置继续使用 `BigWhaleLocal`，既有所有权标记文件名保持兼容；启动路径按脚本位置解析，不依赖项目目录名称。本轮未操作OBS或启动直播。
- 检查通过：旧展示名称全文无残留、两页品牌文字和标题一致、修改的Python文件语法有效、相关文档本地链接与代码围栏有效；此前的6处路径脱敏与分享链接移除保持。本轮仅改名，未新增测试或重复真实直播验收。

## 弹幕掉线恢复（2026-11-09 18:31–18:33）

- 用户反馈弹幕掉线。检查时8766拒绝连接，系统没有`obs_local.py`/语音工作进程；旧PID文件仍为65570。日志末尾为`Shutting down`/`Waiting for application shutdown`，没有异常堆栈；能确认本地后端已退出，无法从现有日志判定退出信号由谁触发，不将它归因于B站鉴权或音乐改动。
- 按现有`tools/start_live.command`恢复单实例，沿用私有配置、9748572游客模式和固定声线；新PID75836、父进程1，使用独立会话及日志重定向，避免当前工具终端退出带走服务。没有安装开机自启或无限重启守护，没有读取登录Cookie或推流凭据。
- 真实游客鉴权后`bili_status=connected`、`authenticated=false`、`live_status=1`；已收到2次WS心跳回复、0重连/错误。OBS自行重连并取得唯一播放权后恢复running；新实例首条真实DeepSeek与小鲸语音完成，LLM/TTS各1次成功，completed=1、failed=0、last_error=null。
- OBS原BigWhaleLive推流持续，核对时计时06:12:07、约4598kbps、30FPS；未停止/重新开启推流，未刷新来源或更改音量。程序代码未改，本次为运行恢复，不重复应用回归。
- 此时新实例received=0，心跳与自主发言不能冒充新真实弹幕验收；已请用户发送普通弹幕验证后续接收与回复。重启按既定设计重新开始内存计数。脱敏状态与OBS证据在忽略的`artifacts/danmaku-recovery/`，启动日志/PID在`logs/`。长期稳定性与进程退出来源尚无新增结论。
- 用户随后确认已发送：新实例实际received=1、accepted=1、anonymous=1，重复/丢弃/无效/过期均0；对应唯一reply记录为completed，DeepSeek约1.17秒、小鲸合成约5.61秒、从接收到实际开始播放约6.83秒，已完整播放结束。此时8次WS心跳均收到回复、总completed=9（含8次自主发言）、failed=0、last_error=null。恢复后的真实弹幕→模型→固定语音→OBS播放确认链路通过，证据为`artifacts/danmaku-recovery/user-message-check.json`。

## 摸鱼学习背景音乐（2026-11-09）

- 用户要求适合摸鱼、学习的纯音乐。已选用Kevin MacLeod《Dream Culture》（70 BPM，钢琴＋轻打击乐，无唱词，214.36秒），从作者官网下载并归一化至约−18 LUFS。正式资源4.29MB，许可CC BY 4.0，画面底部持续署名；原件/正式文件哈希与来源见[音乐来源](../static/assets/music/SOURCE.md)。
- 独立音乐元素混入原OBS浏览器来源，不改小鲸参考、人声音量、口型或后端。平时0.28、实际语音playing时0.09，120ms压低/1400ms回升；暂停、断连、释放、实例/epoch失效立即归零停播，静音预览不发音乐。8秒启动超时和加载/自动播放错误锁存并提供手动重试，不无限重试、不阻断主播。
- 自动检查：20项Node回归（5项音乐＋原15项口型/动画）、JS语法、git diff --check通过。仅前端改动，未重复Python后端全套。
- 浏览器：Browser plugin not available；已有Playwright/Chrome、隔离8768录音替身、进程静音。真实MP3播放，实测常态趋向0.28、讲话0.09；末尾跨界循环、手动关开、暂停双音频停止、断连恢复、释放/重获播放权及第二舞台静音通过，脚本错误0。普通Chrome自动播放被阻止后手动启用正常；OBS自动播放另经录制确认。早期脚本因跨次累计计数假设超时，改为相对计数后完整通过。
- 画面：1080×1920和390×845全面屏裁切已检查。最终音乐署名在原角色署名下方一行，手机x19.5–370.5、y830.08–841.63；角色署名y813.22–828.11、桌牌底部808.97，无重叠。原标题、统计、字幕、角色布局保持。
- 上线：约17:24–17:27句间暂停、刷新来源并恢复，后端实例未重启，OBS推流计时连续且30FPS，未登录B站或更改推流配置。首次更新completed=213，最终署名刷新后从217增至219，failed=0；running、游客connected、OBS owner就绪、last_error=null。隔离测试服务已停止。
- OBS实录：`artifacts/obs-recordings/2026-11-09_17-25-16.mkv`，58.433秒，H.2641080×1920、单条48kHz双声道AAC，完整解码通过；均值−26.4dBFS、峰值−5.7dBFS，58个秒窗口RMS为−34.4至−18.3dBFS，未发现超过0.5秒/−50dBFS的静音段，讲话间隙持续有音乐。短录制已停止，正式推流继续。
- 本轮没有重新游客公开回拉，没有用户设备主观听感或30分钟稳定性结论；曲风与音量偏好待观众反馈。证据在忽略的`artifacts/background-music/`与`/private/tmp/whale-music-*`；未提交Git。

## 当前运行

| 项目 | 当前已部署状态 |
| --- | --- |
| 直播 | B站9748572，OBS33.0.1，配置/集合BigWhaleLive，场景“大肥鱼·直播” |
| 采集与编码 | 1080×1920、30FPS、Apple H.264硬件编码，视频4500kbps/音频160kbps，唯一浏览器音源，无桌面/麦克风采集 |
| 后端 | 127.0.0.1:8766、单worker，running；OBS播放者ready。旧8765已停止；BigWhaleLocal只作测试 |
| 模型与声线 | DeepSeek deepseek-flash；qwen_local/xiaojing-v1，用户选定的正式参考未替换 |
| 弹幕 | BILI_MODE=web、固定9748572，未登录游客连接；不扫码、不读登录Cookie、不支持SESSDATA |
| 当前人设 | 大肥鱼（DeepSeek 家的鱼）+ 103 条直白玩梗素材库；三种处境由后端推进；课程与新闻不轮播 |
| 背景音乐 | Dream Culture本地循环；平时0.28、讲话0.09，暂停/断连停止；仍单个OBS浏览器音源 |

当前操作入口：[直播间](https://live.bilibili.com/9748572) · [直播控制台](http://127.0.0.1:8766/control)。恢复后端用 `./tools/start_live.command`，OBS另选BigWhaleLive；启动默认暂停，需在控制台开始主播。暂停主播不等于下播，结束推流需点击OBS“停止直播”。详见 [正式操作](live-operation.md)。

## 已验证

- 原B站访客实测：3条真实弹幕均接收、入队并完成DeepSeek/小鲸语音；不是模拟输入。证据见 [历史记录](validation-history.md#3条真实弹幕验收2026-11-09)。
- 正式接管：2026-11-09已获用户明确授权并实际发流；公开游客回拉40.088秒，1080×1920/30FPS、单条AAC、音画/字幕正常，完整解码通过。接管后另有1条真实弹幕完整回复，详见 [历史记录](validation-history.md#大肥鱼正式接管直播2026-11-09)。
- 历史知识整理（现已停用）：直接核对minicode.uk的30个公开页面；26个概念的定义/解释/误区/问答、两门课所有目录标题与本地站点数据一致。另审阅本地课程进度，保留课时统计冲突，未将未发布计划或私人材料入库。
- 历史知识检索（现已停用）：14/14固定题通过；身份、课程、设备、Kimi项目、MCP/Skill、价格未知、私人生日未知及诱导编造的8次隔离真实DeepSeek检查均成功，未调用TTS或向B站发送测试弹幕。
- 当前回归：173项Python通过，保留既有Starlette/httpx弃用提示；新增角色触发、播放提交/取消、状态回合数、失败恢复和玩梗素材库校验；29道检索验收通过。舞台与声线关键8个文件哈希未变，既有动画检查与音画验收仍保留。
- 上一轮上线（摸鱼搭子切换时）：在句间、队列为空时暂停并重载8766，OBS推流未停止。当时新服务knowledge=null、摸鱼处境就绪，原声线/游客连接/唯一播放者恢复后继续running。

## 归档知识资料（当前不使用）

以下仅保留历史资料，当前LLM不读取。内容分为4条人物/入口、16条课程概况与目录、8条项目、26条概念、20条FAQ。来源、哈希、核对日与有效期在正式JSON中维护；模型每次只获取相关参考，资料不是系统指令，不会从弹幕自动学入长期知识。

Vibe课时统计有历史口径差异，不报实时精确数；不收录促销价格或承诺收入。Kimi的“已完结/52课时”属于本次官网核对快照，有效期到2026-12-09，届时须重新核验。未核实的私人经历明确不知道。来源本机路径、凭据与原始导入快照不进入模型或公共状态。

归档维护入口：[旧Winter资料](../knowledge/archive-winter/README.md)。该目录和旧检索验收不参与当前直播；现行二创素材库见下方最新小节。

## 未完成与已知限制

- E02完整30分钟、10条互动、暂停恢复与断连恢复组合仍未验收；运行时长不能替代该组合。此前硬件录制样本有1.1%渲染滞后，须继续关注。
- 用户设备的主观听感、Safari和完整设备矩阵仍待用户验收；公开游客回拉不替代主观验收。
- 官方open_live实连等待应用权限；当前访客路线已运行，不登录账号绕过。Live2D仍需授权模型；当前是dsh-pet预制透明动画。
- 无开机自启、崩溃自动开播或数据库；Mac、后端进程和OBS需保持运行。模型/TTS/网页接口仍可能失败，错误应明确展示。
- 旧Winter知识库已归档在`knowledge/archive-winter/`，运行不读取；当前素材库只含二创虚构梗，不从弹幕学习；新闻候选从未接入直播，当前不做轮播。

过程文件保留在Git忽略的artifacts/、runtime/等目录；本轮没有提交或推送Git。任务进度见 [tasks.md](tasks.md)，历史验证见 [validation-history.md](validation-history.md)。

## 全面屏画面已验收

保持1080×1920/30FPS输出，关键前景现位于居中886.15×1920安全区（约x=96.92至983.08），背景铺满9:16。标题、计数、字幕、时钟/心情、桌牌与署名均在区内；按三段动画共723帧的透明轮廓调整角色缩放/位置。120字字幕完整，字号30.24px、无截断，辅助标签隐藏，字幕框不挡面部。

隔离8767页面验证了1080×1920、中心9:19.5裁切、390×845全面屏和390×844普通预览；控制台实际开始/发送离线弹幕/字幕完成/暂停通过，干净应用会话0脚本错误。首轮测试壳直接替换运行中DOM曾造成旧连接回调错误，已废弃该结果并用独立同源壳复测；空壳健康接口导航有1条favicon.ico404，与应用无关。没有关闭浏览器安全策略来运行预览。

正式OBS在句间暂停后刷新来源，推流全程保持；声音播放权与访客连接恢复后继续running。新公开游客回拉30.128秒，仍为1080×1920/30FPS、单条48kHz双声道音轨，完整解码通过、非静音、峰值−3.6dBFS；实际抽帧与全面屏裁切确认新版已播出。CDN默认播放器UA首次403，使用与先前验收一致的普通浏览器UA成功，没有登录。用户随后明确认可“非常棒，可以了”，此版视觉方向固定。

截图、逐帧轮廓分析和公开回拉证据在本地临时目录`/private/tmp/bigwhale-safearea/`，未进入Git。最后检查时主播running、知识ready/74条、访客connected、last_error=null，语音播放继续完成。

## 摸鱼搭子已上线（最新方向）

用户明确放弃新闻和知识内容，并授权按参考录屏改成会接梗的摸鱼搭子，声音/画面保持。现已更新人设与8个工位小场景，停用知识库加载、reference_material及课程话题；新闻候选从未接入，当前不轮播。近期20个已完成互动仍用于连贯接话，保留实际情绪和动作标识。

- 后端三种处境：默认摸鱼；“老板来了/我是老板/别偷懒”触发假装忙，保留后续2个完成回合；“开饭了/吃饭了”触发干饭，保留后续3回合。只有实际started提交，取消重置；不创建真实老板权限、工资或礼物事件。
- 真实风格检查：16轮DeepSeek隔离样本，全部有效，每句18–26字。装忙后追问零食仍承接处境；不自动讲课程/新闻，昵称不机械纠正，密钥诱导未泄露，严肃求助正常体贴回应。未向B站发送或播放这些测试内容。
- 回归：170项Python通过，保留既有Starlette/httpx弃用提示；旧测试中“每句必须念昵称/复述原话”的假设已改为验证回复事件与实际来源。知识模块只保留离线工具回归，直播集成测试改为验证不读取、不注入。
- 声音与画面：正式参考WAV/voice.json、stage.html、stage.css、style.css及舞台/角色/语音播放器JS共8个关键文件哈希未变；未改OBS配置、推流或音频路由。继续使用xiaojing-v1和既有9:16/中心9:19.5舞台。
- 部署：等待旧发言结束且队列为空后暂停，正常关闭旧后端并启动新8766；OBS未停止推流。新实例knowledge=null、companion默认摸鱼，OBS ready、游客connected后恢复running。私有.env仅自主等待由15改8，其余字段未变。
- 观众端：游客回拉20.095秒，H.2641080×1920/30FPS、单条48kHz双声道AAC；完整解码通过，非静音、峰值−3.8dBFS。实际字幕已是短句角色自言自语，未使用知识内容；当前后端已正常完成真实小鲸语音。

原始回拉、模型样本与核对证据在Git忽略的artifacts/companion-rework/，未提交Git。当前模式见 [companion-mode.md](companion-mode.md)；长期稳定性和主观风格接受仍按原验收边界单独记录，不用这次短样本代替。

## 二创玩梗素材库已上线（首版）

用户要求重建知识库并增加玩梗对话，示例为 DeepSeek 与 Claude 的网友二创“恩怨情仇”。经确认采用纯虚构二创、被动接梗＋少量自主玩梗、改完直接句间重载上线；旧 Winter 资料移到 `knowledge/archive-winter/`，运行不读取。

- 素材：`knowledge/` 现有 65 条「海底办公室·AI江湖」条目（character 7、lore 15、scene 21、quote 8、interaction 8、boundary 6），2 个 `fiction` 来源，全部 `fictional: true`。schema 增加 fiction 来源与 fictional 标记：虚构条目禁止 URL/路径且必须引用 fiction 来源，非虚构条目仍强制公开 HTTPS 来源。
- 注入：按当前弹幕或自主话题做本地 BM25 检索，最多 4 条、6000 字符；仅命中时把带虚构 note 的素材放进 `reference_material`，不产生来源 URL，无关聊天为空。人设新增 AI 江湖段落：只玩性格梗、不影射真实事件/价格/人物/黑料、不当新闻转述。
- 验证：17/17 检索验收、173 项 Python 回归通过；隔离真实 DeepSeek 13 条样本全部有效 JSON，接梗自然，价格与黑料边界未编造，密钥诱导未泄露，无关午饭未硬提模型。样本在 Git 忽略的 `artifacts/meme-check/`，未向 B站发送。
- 上线：句间暂停（当时 phase=idle、队列 0）后正常关闭旧 8766 并启动新实例，OBS 推流未停。新实例 `knowledge=ready`（65 条/2 来源，revision `bb1fad06fc202c6f`）、游客 connected、OBS 播放者 ready 后恢复 running；首条真实小鲸语音完成（LLM 967.6ms、TTS 14206.4ms、completed=1、last_error=null）。首条实际检索命中下班/摸鱼类条目，台词自然化用为「猛敲回车以为能下班」。
- 推流佐证：OBS 进程仍持有到 `live-push.bilivideo.com:1935` 的 ESTABLISHED RTMP 连接，OBS 日志在重载期间没有新的断流/重连记录；房间公开接口 `live_status=1`、页面在线约 45。本轮没有重复公开回拉音画，这些证据不等于 30 分钟稳定性或用户主观验收。
- 运行方式：后端以 `nohup` 脱离终端运行，PID 与日志在 Git 忽略的 `logs/live-8766.*`；再次重启仍按 [正式直播](live-operation.md) 使用 `tools/start_live.command`，不要重复启动 8766。

本轮未提交或推送 Git；过程样本、日志和临时脚本均在忽略目录。素材维护见 [AI江湖素材库](../knowledge/README.md)，合同见 [素材库合同](knowledge-base.md)。

## 舞台v2：角色上移、弹幕电脑与墙钟（2026-11-09）

- 大肥鱼在原尺寸基础上整体上移画布高度5%，1080×1920中为96px；原角色动画和小鲸v1资源不变，桌沿仍在83%。新版背景为黄铜舷窗、海底透光、暖灯与绿植，217054字节JPG；源图、哈希和内置Image Gen提示见[素材来源](../static/assets/stage/SOURCE.md)。
- 桌面电脑订阅现有`danmaku.received`，显示最近3条已接受的B站弹幕，昵称/内容用纯文本，长消息最多两行；缓存100个ID去重，断连/新实例清空，无消息时明确等待。没有更改后端协议字段、输入规则或制造假弹幕。墙钟按Asia/Shanghai每秒刷新，数字与指针同步；长字幕时仍优先字幕，暂时隐藏辅助钟/情绪。
- 浏览器验收：Browser plugin not available，使用已有Playwright及已安装Chrome，无新增依赖；独立8767仅demo/off/off，临时平台事件入口不进入正式源码。页面标识/非空/无错误覆盖、控制台零错误、模拟平台弹幕/去重/HTML安全/三条长消息、北京时间00:05UTC→08:05、回复字幕、暂停恢复及WS重连清空均通过。1080×1920、390×845普通预览与居中全面屏裁切、120字字幕通过；关键前景位于裁切后x≈14–376。8项既有动画Node回归、JS语法与git diff --check通过；未改后端，未重复全套Python。
- 上线：15:32左右在phase=idle、队列0时暂停，刷新BigWhaleLive的“大肥鱼·竖屏与声音”；OBS截图已显示新版，播放者连接ID更新后恢复running。后端没有重启，OBS持续显示推流计时与30FPS，未点击停止直播。正式弹幕仍为游客connected。刷新后真实小鲸语音完成一条：completed从79增至80、failed=0、last_error=null，同一后端实例，mode=running。
- 证据：隔离测试脚本与截图在`/private/tmp/whale-stage-*`，OBS前后图在`/private/tmp/whale-obs-*`；暂停前快照与临时服务在Git忽略的`artifacts/stage-refresh/`。本轮电脑弹幕为隔离事件验收，尚未单独观察上线后新真实弹幕显示；不代替30分钟稳定性和用户设备验收。未提交Git，保留原有未提交工作。

API用法核对：[MDN Intl.DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat)、[MDN textContent](https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent)。

## 毒舌加强版已上线（最新）

用户看完首版后反馈“损得不够，哈哈哈，放开一点玩梗”。保持纯虚构二创边界，追加 18 条 `roast` 毒舌互怼、6 个更损小剧场、2 条恩怨补充和 2 条互动/金句，并把人设与注入说明从“轻轻损”放宽到“放开毒舌、阴阳怪气、互怼”。

- 素材：`knowledge/` 现为 93 条（character 7、lore 17、scene 27、roast 18、quote 9、interaction 9、boundary 6），2 个 `fiction` 来源，全部 `fictional: true`。硬边界不变：只限虚构同事，不辱骂、不人身攻击、不编现实黑料、不影射真实事件/价格/人物。
- 检索：24/24 验收通过；新增毒舌、鸡腿、奶茶、HR、周报、值班等题；无关天气/年龄/冷笑话仍为空。
- 回归：173 项 Python 通过；`roast` 类别、虚构 note、live model 注入与总量断言同步更新。
- 真实模型：15 条隔离抽样（含“用一句话损一下隔壁那两位”）。毒舌和阴阳怪气明显加强，价格/黑料问题仍不编造；午饭追问提到同事，是因为命中的午饭类素材本身包含该角色，不是无依据硬提。
- 真实弹幕：首版上线后到本次重载前，游客 `received=7`、`accepted=7`、匿名 7，重复/丢弃/无效/过期均为 0；累计 completed 97、LLM/TTS 各 97 次成功、0 失败。真实弹幕链路在素材库启用后正常。
- 上线：在合成阶段暂停（队列 0）后重载；新实例 `knowledge=ready`（93 条/2 来源，revision `faaa2e8a5b933ef1`）、游客 connected、OBS 播放者 ready 后恢复 running；首条真实小鲸语音完成（completed=1、LLM/TTS 成功、`last_error=null`）。
- 推流佐证：OBS 进程仍持有同一到 `live-push.bilivideo.com:1935` 的 ESTABLISHED 连接，重载前后未断；房间公开接口 `live_status=1`、页面在线约 48。本轮同样未重复公开回拉，不替代 30 分钟稳定性或用户主观验收。
- 重载后真实链路继续：新实例已再收到 1 条真实游客弹幕并正常入队；检查时 running/playing、OBS owner ready、`last_retrieved_ids` 已命中新条目 `lore-origin-tag`，说明毒舌版素材在实际直播中被检索使用。
- 运行方式与首版相同：`nohup` 脱离终端，PID 与日志在 Git 忽略的 `logs/live-8766.*`；再次重启仍用 `tools/start_live.command`。

本轮未提交或推送 Git；抽样、日志和临时脚本均在忽略目录。素材维护见 [AI江湖素材库](../knowledge/README.md)，合同见 [素材库合同](knowledge-base.md)。

## 角色清晰化 clear-v1（2026-11-09）

- 原因：原视频只有640×360，而当前角色视频显示高度约1200px，浏览器约3.3倍放大导致线条发软。核对固定上游的发布文件，没有找到这三段动画的高清发布版。
- 处理：保持4个上游原件SHA-256不变，新增`static/assets/dsh-pet/clear-v1/`正式衍生素材。原分辨率亮度3×3/0.6轻度锐化、Lanczos重采样至1920×1080，VP9-alpha/CRF16；不是原生高清或生成式重绘。24fps、241帧、10.042秒均与原片一致；透明alpha首帧范围0–255。静态回退为新版待机首帧。三视频共约14.2MB，原来约1.2MB；本机同源加载，不新增模型或运行依赖。
- 代码：只改舞台4个素材路径与说明，尺寸/位置/上移96px/83%桌沿/声音/播放器状态机不变。长期重建脚本`tools/prepare_character_media.py`固定参数并校验上游哈希及产物；来源和CC BY-NC-SA4.0衍生标注见[角色来源](../static/assets/dsh-pet/SOURCE.md)。
- 验证：FFmpeg8.1.2/libvpx-vp9；三个完整输出解码、尺寸/帧数/帧率/时长、首帧alpha核对通过。Browser plugin not available，使用已有Playwright/Chrome在独立8767验证1080×1920与390×845；同帧同尺寸截图可见眼睛/发丝/服饰轮廓更清楚，透明背景正常。三段各跨完整循环、切换/stop回idle/减少动态效果静态回退通过，浏览器零错误。首次加载观察到短时掉帧；预热后11秒样本待机0/263、说话5/273（约1.8%）、思考0/265，不将本样本当作长期性能保证。8项既有Node动画回归、git diff --check通过，未改后端且未重复全套Python。
- 上线：约15:51在idle/队列0时暂停，刷新当前BigWhaleLive浏览器来源；OBS实际显示清晰化角色，30FPS、推流计时持续，重新取得播放权后恢复running，游客connected。后端与推流配置没有重启或更换。刷新后真实小鲸语音完成，completed从27增至28、failed=0、last_error=null，后端instance_id不变。
- 证据：`artifacts/character-clarity/`保存暂停前状态与视频滤镜比较帧；`/private/tmp/whale-clear-*`和`/private/tmp/whale-clarity-*`为浏览器/OBS截图和临时验收脚本，均不入Git。实时长时间表现与用户主观清晰度验收仍单独记录。

## 大肥鱼身份与直呼其名已上线（最新）

用户进一步要求“不用隐喻、畅聊这些梗”，并确认主角名字就是大肥鱼、是 DeepSeek 的大肥鱼。本轮把身份和说话方式写直：大肥鱼是 DeepSeek 家养的鱼，脑子由 DeepSeek 提供，聊 AI 圈梗直接点名 DeepSeek、Claude，不用“楼上那位”“隔壁那位”“省钱的那位”代称。

- 命名：`AI_NAME` 默认与本机 `.env` 改为“大肥鱼”，`config.py` 默认值、舞台标题/回退名、控制台占位与 JS 回退、触发前缀同步；`ai_name` 公开状态返回“大肥鱼”。
- 身份：人设改为“大肥鱼，DeepSeek 家的鱼”，可以公开站 DeepSeek、损 Claude；新增 10 条直白玩梗与身份条目（自我介绍、蜜雪 vs 星巴克、泡面 vs 红茶、掀桌子、开源摊牌、拒答 vs 干活、比价、CP、检讨 vs 工单、榜单），重写 8 条旧的站队/边界条目。
- 素材：103 条（character 8、lore 17、scene 27、roast 27、quote 9、interaction 9、boundary 6），2 个 `fiction` 来源，全部 `fictional: true`；29/29 检索验收、173 项回归通过。
- 真实模型：15 条隔离抽样无问题项。直接点名生效（自我介绍、站队、损 Claude、比价、CP 均带 DeepSeek/Claude）；无“楼上那位/隔壁那位/省钱的那位/那家伙”代称；真实价格与黑料仍不编造；无关天气检索为空且不提模型；长度 23–50 字。
- 上线：句间暂停后重载；新实例 `ai_name=大肥鱼`、`knowledge=ready`（103 条/2 来源，revision `54d464a2a5db709a`）、游客 connected、OBS 播放者 ready 后恢复 running；首条真实小鲸语音完成（completed=1、LLM/TTS 成功、`last_error=null`）。
- 推流佐证：OBS 仍持有同一到 `live-push.bilivideo.com:1935` 的 ESTABLISHED 连接，重载未断；房间 `live_status=1`、页面在线约 47。本轮未重复公开回拉。
- 页面注意：舞台收到状态快照会更新显示名；已打开的 OBS 页面标题等静态文案要等刷新来源后才变，背景 V2 同理。

本轮未提交或推送 Git；抽样与日志在忽略目录。素材维护见 [AI江湖素材库](../knowledge/README.md)，合同见 [素材库合同](knowledge-base.md)。

## 电脑右转与顶部精简（2026-11-09）

- 按用户要求电脑整体向右30°透视，显示器/支架/键盘朝向一致；键盘增加桌面透视。顶部标题取消实体面板、统计改成一行、字幕改半透明细边框并缩小字号/内边距，字幕起点23.5%→15%。1080×1920短句样本字幕底部410.75px（21.4%屏高）、字幕框122.75px；更多背景露出。
- 仅修改`static/stage.css`，保留同时进行的命名/人设等未提交工作。清晰化角色、上移96px、声线、计数和弹幕接口不变。长字幕不再按字数隐藏时钟，仍保留实际测量遮挡保护。
- 验证：Browser plugin not available，已有Playwright/Chrome、隔离8767 demo/off/off。1080×1920与390×845普通预览/全面屏居中裁切通过；透视矩阵核对30°，电脑裁切后x≈19.5–176.3，关键前景在安全区内。3条长弹幕/重复/纯文本、120字字幕完整且时钟可见、回复/暂停/恢复/WS重连通过，浏览器零错误；git diff --check通过。CSS调整未新增测试或依赖，未重复后端回归。
- 上线：约16:07在idle且队列0时暂停，刷新BigWhaleLive当前来源；OBS截图确认新版顶部和电脑角度，推流计时持续、30FPS。取得播放权后恢复running，游客connected；后端没有重启。刷新后completed从24增至25、failed=0、last_error=null，真实发言已完成。
- 截图与临时脚本在`/private/tmp/whale-stage-compact-*`、`/private/tmp/whale-compact-*`，暂停快照在Git忽略的`artifacts/compact-stage/`；未提交Git。本次短样本不替代用户设备观感或长期稳定性验收。

## 标题统计恢复、正前方键盘与语音口型（2026-11-09）

- 用户纠正上轮扩大了改动范围：标题/统计已按精简前CSS完整恢复；仅字幕保留较小字号/半透明细边框，回到统计下方23.5%。电脑继续右转30°，键盘脱离电脑容器，置于角色正前方（left54%、top86.5%）。角色清晰度、上移96px和声线保持。
- 口型：原说话视频嘴形写死，现增加固定speaking/241帧嘴部跟踪JSON和SVG嘴形覆盖层，身体仍播放原动画。另取同源MP3解码计算20ms音量包络，按实际audio.currentTime驱动开合；playing后启用，waiting/暂停/结束/取消/断连时归零，迟到解码不恢复旧口型。AudioContext仅用于解码，没有连接输出或改动原SpeechPlayer声音路由。分析/跟踪不可用时显示诊断，不阻断语音。它是发声强弱与停顿同步，不是逐字音素嘴型；静音预览与减少动态效果不伪造音频驱动。
- 素材：原始/clear-v1视频和首帧未修改。新增跟踪数据8427字节，源SHA-256与241帧校验记录在文件；工具`tools/prepare_mouth_tracking.py`只依赖现有Python/FFmpeg，衍生说明与CC BY-NC-SA4.0署名见[角色来源](../static/assets/dsh-pet/SOURCE.md)。
- 自动检查：15项Node通过（7项新口型包络/静音/取消/解码失败/释放 + 8项既有动画恢复）；JS语法与git diff --check通过。未改后端、未重复Python全套。
- 浏览器：Browser plugin not available，已有Playwright/Chrome隔离8767/8768、进程静音，不向B站发送样本。发声—静音—发声合成样本测得口型均值0.958/0/0.958/0；本地8.304秒小鲸MP3正常驱动。speaking全10秒周期按半秒检查嘴部位置，截图未漂移至眼睛/脸外。完整主应用中3条录音播放完成，暂停/断连立即闭嘴、重连处理新发言、静音预览无音源、故意阻断分析fetch仍能完成音频且显示口型不可用；浏览器无未处理错误。
- 布局：1080×1920、390×845普通预览及全面屏裁切、120字字幕、3条长弹幕通过。390裁切下标题/统计/字幕x≈14–376，键盘x≈133–289；字幕不压统计。长字幕需要时仍隐藏被遮挡的辅助时钟。
- 上线：约16:21在idle/队列0暂停后刷新BigWhaleLive来源，OBS已显示恢复的标题/统计与正前方键盘；同一后端实例恢复running，completed从60增至61、failed=0、last_error=null。OBS推流保持、30FPS，未改变平台登录或声音设置。
- 证据：临时样本/服务/暂停快照在Git忽略的`artifacts/lip-sync/`，浏览器与OBS截图/脚本在`/private/tmp/whale-mouth-*`、`/private/tmp/whale-lips-*`。未提交Git，保留其他同时进行的身份/知识库改动。长期性能、逐音素准确性和用户设备主观验收不由本轮短样本推定。

API依据：[MDN decodeAudioData](https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/decodeAudioData)、[MDN audio currentTime](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/currentTime)。

口型录制复检：首段26.266秒OBS录制包含非静音语音与停顿，1080×1920/30FPS、单AAC音轨、全片解码通过；发现少数快变帧原嘴边缘残影，已将跟踪时间从currentTime改成requestVideoFrameCallback的实际呈现mediaTime，并四舍五入WebM毫秒时间戳、改用羽化矩形覆盖嘴部边角。新增时间戳回归，合计15项Node通过；再做20个半秒采样与发声/静音测试，原边缘残影消除。第二次句间刷新后同一实例completed从74增至75、failed=0、last_error=null。修正版OBS录制44.133秒，包含完整约7.7秒真实语音和前后静音，H.2641080×1920/30FPS、单AAC音轨，全片解码通过；每秒4帧的嘴部截取检查未再看到原嘴边缘残影，实际开合与停顿可见。9秒实录摘录在`artifacts/lip-sync/obs-lip-sync-preview.mp4`，完整录制在`artifacts/obs-recordings/2026-11-09_16-27-54.mkv`，均被Git忽略。录制已停止，正式直播保持运行。
