# bilive-danmaku 网页读取方式

- 来源：[Beats0/bilive-danmaku](https://github.com/Beats0/bilive-danmaku)。
- 研究版本：`5861f8e70035df1030e82d90c53c6475779d3b15`，上游版本 1.0.11。
- 授权：MIT，Copyright (c) 2020 Beats0；完整许可保留在 [LICENSES](../../LICENSES/bilive-danmaku-MIT.txt)。
- 相关源码：[API/WBI](https://github.com/Beats0/bilive-danmaku/blob/5861f8e70035df1030e82d90c53c6475779d3b15/src/renderer/api/index.ts)、[Socket](https://github.com/Beats0/bilive-danmaku/blob/5861f8e70035df1030e82d90c53c6475779d3b15/src/renderer/components/Danmaku/base/Socket.ts)、[消息字段](https://github.com/Beats0/bilive-danmaku/blob/5861f8e70035df1030e82d90c53c6475779d3b15/src/renderer/components/Danmaku/MsgModel.ts)。

用户于2026-11-09明确授权在开放平台申请期间使用此项目的方式，固定读取房间9748572。没有安装完整Electron应用；在现有Python后端独立实现同等读取链路，参考其WBI排列表、参数过滤、加入房间包和DANMU_MSG字段位置。没有导入其图标、字体、界面或翻译/朗读模块。

链路为：SPI获得匿名buvid → nav获得WBI图像密钥（不登录） → 安全解析房间网页的JSON以确认实际房间 → 签名getDanmuInfo → 向返回的B站弹幕WSS发送操作7鉴权包 → 操作2/3心跳及操作5消息。网页包头版本1、序列1，加入房间声明protover=3，支持有界Brotli解码；普通文本取info[1]，用户取info[2]，时间取info[0][4]。

新增的边界包括HTTP/WS总时限、大小及递归深度限制、WSS主机/端口校验、稳定期后重置的有界故障重连、暂停消息ID记录、全程文本渲染和敏感参数脱敏。网页模式没有Open Live应用场次，不调用start/end或应用HTTP心跳。只读取，不发送弹幕、礼物或其他互动。

用户明确禁止登录其B站账号，因此没有导入上游的扫码登录模块，不读取浏览器登录Cookie，也不配置SESSDATA。若平台隐藏用户身份，文本仍按匿名消息接收；使用明确的房间匿名限流组，共用5秒冷却，而非伪造真实UID或从昵称推导身份。平台停止向访客推送时只报告失败，不改用登录绕过。官方申请完成后仍可显式切回open_live。
