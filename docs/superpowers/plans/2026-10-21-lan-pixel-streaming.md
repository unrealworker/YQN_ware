# 内网像素流启动器 Implementation Plan

> **For agentic workers:** Use subagent-driven-development with independent package, server/player, and launcher tasks, then integrate and verify actual WebRTC video.

**Goal:** 打包当前 Zcool 仓库场景，交付可双击的 Windows 本地启动器，内网网页自动播放，最多三人并支持共享或独立实例。

**Architecture:** UE 5.4 原生 PixelStreaming + 与 UE5.4 匹配的 Epic 前端；Node 负责 HTTP/WebSocket 信令、最多三个访问者、UE 子进程和本机控制接口；WinForms 启动器配置和监控服务。所有运行时文件随交付目录提供，关闭只结束本启动器拥有的进程树。

**Tech Stack:** Windows / UE5.4 / MSVC14.38 / .NET Framework4.8 WinForms / bundled Node / Epic UE5.4 frontend.

**Spec:** 本轮用户消息。新增确认：共享同一个场景或每人独立场景必须在启动器可设置。

## Global Constraints

- 当前地图和全部已完成HUD功能必须打包；不回退用户未提交的修改。
- 启动器设置 executablePath、httpPort（默认8080）、streamerPort（默认8888）、showWindow、width（默认1920）、height（默认1080）、mode（shared/independent），默认60fps，最多3访问者。
- “不打开程序”表示 UE 仍运行，以 RenderOffscreen 无本地窗口渲染。
- 浏览器自动连接并静音播放；以实际连接阶段/首帧更新进度，不伪造模型加载百分比。
- 第四名已接纳访问者替换最早接纳者，退出者收到中文通知且停止自动重连，不能循环抢占。
- 共享模式1个UE实例，独立模式按需最多3个。模式在停止状态切换。
- 开启自动启动所需服务和UE；停止/关闭启动器结束所拥有的服务和UE，不能按进程名误杀其他UE/Node。
- 控制API仅绑定loopback且令牌保护；公网无管理接口，静态文件不能任意读取本地路径。
- 内网部署仅针对本地网段，必要防火墙规则使用程序/端口和LocalSubnet范围。

## Review Focus

- 非法/占用端口和带空格/中文路径；必须可读提示且不杀占用者。
- 第4人和被替换者重连竞态、刷新/断网幽灵连接；必须保持<=3且通知明确。
- UE/信令异常退出、启动失败、关闭启动器；必须清理已拥有实例并可再次启动。
- 自动播放、首帧、输入和非1080p浏览器；不能以WebSocket连接成功代替视频验收。
- 独立模式三实例资源消耗；实测并披露分辨率/FPS边界，不声称任意网络都60fps。

## Task 1: 当前项目打包

- 检查最新日志与实际target，启用UE5.4 PixelStreaming插件。
- 以当前代码和地图构建TestGame，定向cook目标地图，保留CEF/字体/HTML/数据目录。
- 输出 `Deployment/GHSPixelStreaming/App/Windows/`，记录UAT日志和进程退出码。
- 验证packaged程序实际启动、HUD和PixelStreaming模块加载。

## Task 2: 服务和浏览器

- 源码目录 `Tools/PixelStreaming/server/` 与 `Tools/PixelStreaming/player/`，测试 `Tools/PixelStreaming/tests/`。
- 使用固定版本Epic UE5.4前端核心，保留许可证和版本证据。
- Node CLI `server.js --config <json> --control-file <json>`；启动令牌从 `GHS_CONTROL_TOKEN` 环境变量读取。
- config包含上列字段及可选fps=60、minBitrateMbps=8、startBitrateMbps=20、maxBitrateMbps=35；Node可执行和网页以相对部署目录寻址。
- control-file写入 `{controlPort,pid,httpPort,streamerPort}`；loopback控制HTTP端点 GET `/status`、POST `/stop`，Header `Authorization: Bearer <token>`。
- status包含state、message、mode、viewerCount、maxViewers=3、instances（id,pid,state）、urls、logs（最近100行）；停止响应后优雅清理并退出。
- HTTP公开网页和只读health，WS玩家连接走同端口；UE streamer只监听loopback streamerPort。
- tests覆盖端口、admission先入先出、踢出通知/不重连、独立实例路由、管理认证、退出清理。

## Task 3: Windows 本地启动器

- 源码 `Tools/PixelStreaming/launcher/`，build脚本产出部署根 `GHS像素流启动器.exe`。
- 中文表单、选择EXE、端口检测、模式选择、窗口开关、分辨率、开始/停止、复制/打开内网地址、在线人数与日志。
- 使用Json序列化保存配置；node作为受控子进程通过Windows JobObject追踪，关闭杀自身树，不扫描/杀其他应用。
- 只读监控Node控制接口；重入/双击启动锁定；关闭时停止服务并等待/兜底回收。
- 测试配置校验、中文空格引号路径、端口占用错误、启动失败回滚、重复启动/停止。

## Task 4: 集成与实际浏览器验收

- 固定运行时与依赖复制至部署目录，不需要用户安装Node/npm。
- 检查内网IPv4、指定端口、GPU编码能力；最小范围防火墙配置。
- 实际packaged UE→网页首帧、1920x1080视频、FPS/码率、鼠标输入和HUD。
- 4个真实浏览器会话验共享容量替换；再验独立模式视角不互相影响及实例回收。
- 启停/端口占用/关闭清理后端口可重新使用。
- 最终交付启动器、访问地址、中文说明、验证报告；说明无法从本机替代第二台物理内网客户端的验证。
