# 大肥鱼角色素材来源

来源项目：[PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)。

固定上游版本：`6d110d013922fde7ff72e4a910365fae6bbb0835`。每个文件的来源路径、上游 Git blob 哈希与本地 SHA-256 见 [manifest.json](manifest.json)。这些文件是项目正式角色素材，应纳入 Git；下载缓存、检查截图及临时解码文件仍按项目规则忽略。

## 署名和授权

- 桌宠项目作者：[PC2005-cloud](https://github.com/PC2005-cloud/dsh-pet)。
- 角色原型「溟月」：[B站 上善无形](https://space.bilibili.com/4456176)。
- DeepSeek 版女仆鲸鱼娘设计：[B站 ZipZipPipe](https://space.bilibili.com/4168597)。
- 这是社区二创的「大肥鱼／鲸鱼娘」，不是 DeepSeek 官方形象。
- 上游代码标注为 MIT，角色素材单独标注为 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans)，即署名、非商业、相同方式共享。以[固定版本 README 的许可说明](https://github.com/PC2005-cloud/dsh-pet/blob/6d110d013922fde7ff72e4a910365fae6bbb0835/README.md#许可)和[上游引用的形象授权声明](https://www.bilibili.com/opus/1247156596114456581)为依据；代码的 MIT 不替代角色素材授权。

## 本项目采用的内容

| 本地文件 | 上游原文件 | 用途 |
| --- | --- | --- |
| idle.webm | 待机呼吸休闲.webm | 待机与暂停时的角色动画 |
| speaking.webm | 碎碎念-对屏碎碎念.webm | 展示台词期间的说话动画 |
| thinking.webm | 工作状态-思考冒泡.webm | 生成台词时的思考动画 |
| poster.png | 待机呼吸休闲.webm 的首帧 | 加载占位、减少动态效果及 Safari 静态回退 |

三个 WebM 仅重命名，字节与上游文件一致。poster.png 使用 FFmpeg 的 libvpx-vp9 解码器提取原视频完整首帧为 RGBA PNG，没有重绘、裁剪、改色或背景替换。本项目播放器独立实现，没有安装或运行上游 DSH 插件及其模型、语音或桌面组件。

原视频是 640×360 的 VP9-alpha 透明动画。说话动画按字幕状态切换，不能视为 Live2D 或精确口型同步。浏览器若无法播放或用户偏好减少动态效果，则使用同一角色的透明首帧；Safari 根据上游记录的透明 WebM 限制直接使用静态首帧。

## 当前播放衍生版 clear-v1（2026-11-09）

用户要求改善放大后的模糊。上述上游原件与校验值完整保留；舞台现引用`clear-v1/`中的透明播放副本及首帧。衍生版沿用 **CC BY-NC-SA 4.0**，保留作者和角色署名，修改者为本项目；不是上游原生高清资源或新的角色设计。

- 对原始亮度做轻度3×3锐化（0.6），色度与透明通道不锐化，再用Lanczos重采样到1920×1080。
- 三段视频均保持24fps、241帧、10.042秒，不插帧、不更换动作、不改变位置与大小。VP9-alpha、CRF16；静态回退从新版待机视频提取RGBA首帧。
- 这是对原640×360素材的重采样与锐化，改善放大线条，不等于恢复原生1080p细节。未使用生成式重绘。
- 每段来源/输出哈希、大小与验证参数见[衍生清单](clear-v1/manifest.json)。工具为FFmpeg8.1.2/libvpx-vp9，重建：`.venv/bin/python tools/prepare_character_media.py`；工具先核对上游哈希，再核对尺寸、帧数、帧率、时长和首帧透明通道。
- 根目录中的原始视频及原始poster保持不变；回退时仅将stage.html的四个素材路径切回根目录。

## 语音口型覆盖层（2026-11-09）

用户要求嘴形与语音对上。新增`mouth-tracking.json`，从固定原始speaking.webm逐帧定位嘴部中心/覆盖范围并取邻近肤色，241帧、24fps，记录源SHA-256；重建工具`tools/prepare_mouth_tracking.py`校验原件哈希，不修改视频。浏览器按实际帧位置覆盖原嘴部、用SVG绘制随语音强弱开合的嘴形，身体与手势仍来自原动画。衍生跟踪数据与角色表现沿用CC BY-NC-SA4.0及上述署名；前端代码独立实现。它是强弱/停顿同步，不是逐音素嘴型或Live2D。原始与clear-v1视频/首帧均保持不变。
