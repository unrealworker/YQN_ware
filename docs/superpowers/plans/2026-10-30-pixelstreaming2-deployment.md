# UE 5.8 PixelStreaming2 与启动器迁移计划

**目标：** 将现有项目切换到 UE 5.8.4 PixelStreaming2，更新同风格启动器配置，重新打包部署到原服务器，并在新版本通过后清除旧包和 peer-stream。

**架构：** 使用已安装引擎的 PixelStreaming2 / EpicRTC 和匹配 UE5.8 的前端。保留当前会话管理、十人上限、访问保护、中文搜索和 HTTPS 入口。源码改动在现有升级工作树执行，完成后中文提交并安全合入 master。

**用户规格：** 三个配置项必须位于像素流启动器，分别是异步编码、NVIDIA 编码器、固定 FPS 默认 60；沿用原来的蓝白深蓝界面风格。部署到 10.100.185.161 的 C:/YQN_WareHouse，入口 warehouse-sim.iyunquna.com。

## 技术约束与设计

- UE5.8 原版 PS2 没有 PixelStreamingEncoderAsync 和 PixelStreamingEncoder=NVIDIA 两个原生开关，不能直接拼接无效命令后宣称生效。
- 异步选项明确标为“异步采集（与渲染解耦）”，使用真实 DecoupleFramerate；不声称启用了另一种 NVENC 异步驱动模式。
- 编码器提供 NVIDIA / 自动，默认 NVIDIA；显式要求 NVIDIA 时校验渲染设备与硬件条件并报告失败，避免静默回落。
- 固定帧率默认开启、60 FPS，同步渲染与采集目标，禁止动态预算同时改写；不使用会改变回放时钟速度的固定模拟步长。
- 保留服务器当前入口、TLS、TURN、访问保护和用户配置；迁移新增字段并清除 peer 对比入口。日志不输出凭据。
- 新包完成构建、真实画面及输入验证前不删除旧运行包；删除仅限核对过的项目交付包、旧暂存包和 peer 文件，不动源码、Content、系统依赖或其他程序。

## 步骤与验收

- [x] 适配项目模块、输入组件、DataChannel、运行指标、FPS预算到PS2，明确弃用Legacy补丁。
- [x] 启动器新增设置、保存/恢复/校验、运行中禁改与重启提示；配置和服务单测、C#自检及实际界面截图通过。
- [x] 升级并固定前端SDK依赖，更新协议和统计适配，验证中文搜索与会话管理。
- [x] 移除peer-stream入口、代理、构建和交付依赖；回归管理员断开、重连与人数限制。
- [x] UE Editor与Shipping编译、完整Cook/Stage/Archive；本地实际H264视频和交互验收。
- [ ] 服务器暂存整包、哈希核对、保留当前配置、停服切换；确认真实PS2运行、固定域名画面与输入。
- [ ] 根据实测列明已验证/限制；删除确认过的本地与远端旧包，记录删除清单；中文Git提交并交付。

## 审查重点

1. PS2原生参数是否确实存在，UI语义和实际行为是否一致。
2. NVIDIA条件不满足时必须清晰失败；固定FPS与预算不得相互覆盖。
3. 前端与PS2协议、中文输入、统计字段及初始化顺序必须实际验证。
4. 旧配置和TLS/TURN秘密不可覆盖、打印或丢失。
5. 删除边界和先后顺序，确保旧包不先于新包验证被删除。

## 本地验证记录（2026-10-30）

- UE5.8.4 Editor 编译成功；Shipping 完整构建、Cook、Stage、Archive 成功，主地图 SHA256 不变。
- GHS.Streaming 原生自动化 7/7；Node 全回归 111/111；启动器 C# 自检 57/57；GUI smoke 通过。
- 真实本机浏览器接收 1920×1080、约 60 FPS，内网 UDP，近期丢包 0%；这不代表服务器多实例容量。
- 中文“人工叉车”通过 DataChannel 返回 16 个结果，点击 FORK-01 展开屋顶并定位；管理员断开后页面停止自动重连。
- 实连发现并补齐 UE5.8 SDK 的 layerPreference 报文，保留其他非法信令拒绝。
- 交付运行库已改用 UE5.8 官方 vc_redist.x64.exe 与 GameInputRedist.msi；新安装器保留配置，异常回滚，历史备份待服务器验证后清理。
- 本地证据位于 Saved/PS2Migration 与 Saved/PixelStreaming/UE58LauncherReview（不入 Git）。
