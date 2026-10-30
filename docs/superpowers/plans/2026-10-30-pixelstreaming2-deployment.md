# UE 5.8 PixelStreaming2 与启动器迁移计划

**最新结论（2026-10-30，UTC+8）：** 用户修复服务器 EIP 媒体地址后，本机经固定域名收到 1920×1080 首帧并持续播放，屋顶点击交互通过。当前画质流畅度仍未达到稳定 60 FPS。保持现有 UE5.8 和用户的服务器修改；用户已取消回滚，服务器旧包保留备份，不继续删除。

**目标：** 将现有项目切换到 UE 5.8.4 PixelStreaming2，更新同风格启动器配置，重新打包部署到原服务器。peer-stream 已从新交付方案移除；旧包处置以最新保留备份指令为准。

**架构：** 使用已安装引擎的 PixelStreaming2 / EpicRTC 和匹配 UE5.8 的前端。保留当前会话管理、十人上限、访问保护、中文搜索和 HTTPS 入口。源码改动在现有升级工作树执行，完成后中文提交并安全合入 master。

**用户规格：** 三个配置项必须位于像素流启动器，分别是异步编码、NVIDIA 编码器、固定 FPS 默认 60；沿用原来的蓝白深蓝界面风格。部署到 10.100.185.161 的 C:/YQN_WareHouse，入口 warehouse-sim.iyunquna.com。

## 技术约束与设计

- UE5.8 原版 PS2 没有 PixelStreamingEncoderAsync 和 PixelStreamingEncoder=NVIDIA 两个原生开关，不能直接拼接无效命令后宣称生效。
- 异步选项明确标为“异步采集（与渲染解耦）”，使用真实 DecoupleFramerate；不声称启用了另一种 NVENC 异步驱动模式。
- 编码器提供 NVIDIA / 自动，默认 NVIDIA；显式要求 NVIDIA 时校验渲染设备与硬件条件并报告失败，避免静默回落。
- 固定帧率默认开启、60 FPS，同步渲染与采集目标，禁止动态预算同时改写；不使用会改变回放时钟速度的固定模拟步长。
- 保留服务器当前入口、TLS、TURN、访问保护和用户配置；迁移新增字段并清除 peer 对比入口。日志不输出凭据。
- 保留用户服务器 EIP 媒体地址修改和现有 UE5.8 部署；取消回滚与后续远端旧包删除。此前已完成的本地清理单独记录，不动源码、Content、系统依赖或其他程序。

## 步骤与验收

- [x] 适配项目模块、输入组件、DataChannel、运行指标、FPS预算到PS2，明确弃用Legacy补丁。
- [x] 启动器新增设置、保存/恢复/校验、运行中禁改与重启提示；配置和服务单测、C#自检及实际界面截图通过。
- [x] 升级并固定前端SDK依赖，更新协议和统计适配，验证中文搜索与会话管理。
- [x] 移除peer-stream入口、代理、构建和交付依赖；回归管理员断开、重连与人数限制。
- [x] UE Editor与Shipping编译、完整Cook/Stage/Archive；本地实际H264视频和交互验收。
- [x] 服务器暂存整包、哈希核对、保留当前配置、停服切换；服务器内 Edge 经固定域名收到真实 PS2 视频，点击屋顶交互通过。
- [x] 本机经固定域名接收服务器视频：EIP 媒体候选修复后，1080p 首帧、约 115 秒持续播放、数据通道及屋顶点击交互通过。
- [x] 记录已验证项和限制、本地清理结果；远端旧包按最新指令保留备份，不继续回滚或删除。
- [ ] 稳定 60 FPS 画质流畅度验收：本机闭顶首页可见窗口仍有明显丢包与解码帧率下降，不能宣称已经达标。

## 审查重点

1. PS2原生参数是否确实存在，UI语义和实际行为是否一致。
2. NVIDIA条件不满足时必须清晰失败；固定FPS与预算不得相互覆盖。
3. 前端与PS2协议、中文输入、统计字段及初始化顺序必须实际验证。
4. 旧配置和TLS/TURN秘密不可覆盖、打印或丢失。
5. 删除边界和先后顺序，确保旧包不先于新包验证被删除。

## 本地验证记录（2026-10-30）

- UE5.8.4 Editor 编译成功；Shipping 完整构建、Cook、Stage、Archive 成功，主地图 SHA256 不变。
- GHS.Streaming 原生自动化 7/7；Node 全回归 111/111；启动器 C# 自检 57/57；GUI smoke 通过。
- 此前本机 localhost 实连接收 1920×1080、60.3–60.5 FPS，UDP，近期丢包 0%；这是本机运行包自测，不是本机到阿里云的链路结果，也不代表服务器多实例容量。
- 中文“人工叉车”通过 DataChannel 返回 16 个结果，点击 FORK-01 展开屋顶并定位；管理员断开后页面停止自动重连。
- 实连发现并补齐 UE5.8 SDK 的 layerPreference 报文，保留其他非法信令拒绝。
- 交付运行库已改用 UE5.8 官方 vc_redist.x64.exe 与 GameInputRedist.msi；新安装器保留配置，具备异常回滚能力；服务器历史包按最新指令保留备份。
- 本地证据位于 Saved/PS2Migration 与 Saved/PixelStreaming/UE58LauncherReview（不入 Git）。

## 服务器验证记录（2026-10-30）

- 已将 UE5.8.4 / PixelStreaming2 包安装到 `10.100.185.161` 的 `C:\YQN_WareHouse`，新版启动器已运行。安装器核验并安装 211 个文件，结果为 `installed`，保留原配置；清单 SHA256 为 `34ac4506574317f6122baa104829508ce6146fd7f0eceb8481b7e3ba55b4a0cb`。
- 服务器实际 GPU 为 NVIDIA L20-16Q、16 GiB，驱动 538.78。运行指标确认 `streamingPlugin=PixelStreaming2`、`encoderPolicy=NVIDIA`、`nvencApiValidated=true`、渲染目标与采集目标均为 60、异步采集已开启。
- 在服务器自身的 Edge 访问 `https://warehouse-sim.iyunquna.com/`，实际收到 1920×1080 视频；闭顶截图接收帧率 57 FPS，点击展开屋顶后截图为 52 FPS，显示内网 UDP、近期丢包 0%。屋顶展开后内部设备与 POI 正常显示，证明本轮输入确实抵达运行场景。
- 后续开顶状态的一次原始指标采样为实际渲染 45.17 FPS、GPU 18.09 ms、Game 1.24 ms、Render 2.65 ms。这些是不同时间点的采样，不能作为同一窗口平均值比较。配置的 60 FPS 是目标上限，并不保证复杂场景持续达到 60 FPS；本轮未做十实例容量验收。

### 最新本机验证（21:04–21:08，UTC+8）

- 用户修复服务器 EIP 公网媒体地址后，本机仍使用 `https://warehouse-sim.iyunquna.com/`，连接与 ICE 均为 `connected`，实际选中 `srflx / UDP / 47.96.135.179:50001`，收到 1920×1080 视频。首个采样已解码 240 帧、报告 50 FPS、RTT 16 ms、丢包 0。
- 后续视频播放时间达到约 115 秒，累计解码 5,092 帧，数据通道为 `open`；此时已出现明显丢包。不能将初始零丢包采样当成持续稳定性的证明。
- 闭顶首页、页面可见的 12.007 秒独立窗口：平均解码 33.73 FPS、平均接收 48.06 FPS、视频码率约 11.15 Mbps、RTT 18 ms；RTP 接收端报告的窗口丢包比例约 35.54%。该采样不在屋顶展开后，不能归入开顶场景性能数据，也不能据此精确定位丢包来源。
- 随后本机点击主仓库 POI，屋顶消失、内部设备 POI 正常显示；交互另有截图证据，不与前述闭顶采样混用。
- 当前可确认的是：EIP 提供可达媒体候选后连接成功，仍需改善持续播放质量；不泛称是用户 VPN 或整条网络故障，不宣称稳定 60 FPS。

### 早期网络检查与保留事项

- EIP 修复前，本机网页与 WebSocket 信令可通，但未收到视频，媒体接收 0 字节。域名经 ALB 提供 HTTPS；禁用代理和使用本地代理访问 `/health` 均为 HTTP 200，当时直连私网服务器 8080 超时；这些仅是早期检查，不能代表修复后的媒体状态。
- 早期独立 UDP 定点测试中，服务器 `10.100.185.161:50199` 已绑定，本机连续发送 4 次均超时，服务器 `received=0`、`echoed=0`；只确认当时被测私网 UDP 路径不通，未定位具体阻断层。同期 `local-final-ice-proof.json` 没有候选对，不作为完整 UDP/ICE 协商证据；后续 EIP 候选已实际连通。
- 固定域名的 HTTPS 网页/信令与 WebRTC 视频媒体使用不同链路。能打开网页不等于客户端已能到达服务器的媒体候选地址与 UDP 端口。服务器内 Edge 成功，也不能代替本机跨网络的视频验收。
- EIP 修复前对照旧配置，12 项入口、网络和访问配置均未改变，旧、新配置均有 STUN、均没有 TURN。该对照是历史快照，不覆盖用户随后修改的服务器配置；当前已通过 EIP 的 UDP 候选收到视频，不再将“媒体不通”列为现状。
- 本地旧包清理已完成，净释放 5,906,141,445 字节（约 5.50 GiB），保留约 41 MiB 的配置、日志与源码文本；peer 部署目录已移除，旧 peer 进程 PID 46720 已停止。用户编辑器 PID 20948 占用的约 481 MiB 旧插件 Binaries 暂留，未强行关闭编辑器。清理证据为 `D:/UEPro/Test/Saved/PS2Migration/cleanup-local-packages-result.json`，最终错误列表为空。
- 此前服务器清理助手已传到 `C:\YQN_WareHouse\diagnostics\cleanup-server-old-deliveries.js` 并运行 `--plan`，结果未读取；`--apply` 未执行。用户现已要求保留远端旧包备份，不继续旧包删除。
- 回滚助手只在本地准备，未在服务器执行 `--stage` 或 `--apply`；回滚已取消，保持现有 UE5.8 与用户服务器修改。本次文档更新未操作浏览器、生产代码或服务器。
- 此前浏览器被用户接管时已停止远程操作；该暂停记录仅说明当时的操作边界，不改变后续 EIP 修复后的成功验证结果。
- 主目录 Editor 的另一次链接被用户正在运行的编辑器 PID 20948 占用 DLL 阻断；工作树 Editor 编译和已交付 Shipping 构建均已成功，不能将该占用误记为新运行包构建失败。

最新证据位于 `Saved/PS2Migration/`：`local-eip-verification.json`、`local-eip-sustained.json`、`local-eip-visible-window.json`、`local-eip-roof-interaction.png`。早期证据包括 `server-install-proof.json`、`server-media-verified.json`、`server-network-comparison.json`、`server-domain-video-stats.png`、`server-roof-interaction.png`、`server-udp-probe.json`、`local-udp-probe.json`；`local-final-ice-proof.json` 仅记录当时未建立候选对的状态。记录不复制凭据、令牌或日志全文。简要验收见 `docs/PixelStreaming2-UE58-部署验收-20261030.md`。
