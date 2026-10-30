# GHS 项目级 Pixel Streaming 补丁

本补丁以 UE **5.8.4，CL 58902052** 的原始 Legacy PixelStreaming 插件为基线，放在 `Plugins/PixelStreaming`，由项目插件覆盖同名引擎插件。未修改引擎安装目录。Epic 原版权头、模块结构、资源和内容保留，使用项目原有 Unreal Engine 许可。本次由 UE5.4 补丁重新移植，未切换到 PixelStreaming2。

## 收录范围

- 官方原始收录总计 251 个文件、1,150,554 字节，包含 `Source`、`Config`、`Content`、`Resources` 和 `.uplugin`。
- 不收录 `Binaries`、`Intermediate`、下载后的 WebServers 或 Node 依赖。资源中原有的小型下载脚本保留，但本任务不执行下载。
- `source-manifest.json` 记录每个文件的原始引擎 SHA256、项目 SHA256，以及是否修改。新增 policy、测试和忽略规则的原始哈希为空。

## 启动参数

| 参数 | 行为 |
| --- | --- |
| `-PixelStreamingWebRTCFps=0` | 移除 RTP `max_framerate` 可选值；强制采集帧驱动推送；跳过插件内部 layered encoder 固定帧率丢帧器。 |
| `-PixelStreamingWebRTCFps=60` | 保留原有正数帧率限制语义，便于对照。 |
| `-GHSLowLatencyPlayout` 或 `-GHSLowLatencyPlayout=true` | 硬编码 H264/AV1 包请求接收端 `playout_delay` 最小/最大均为 0 ms，尽快显示。 |
| 不传上述 playout 参数，或 `-GHSLowLatencyPlayout=false` | 保留 WebRTC 默认接收缓冲策略。默认关闭，便于 A/B。 |

对应运行时变量为 `PixelStreaming.WebRTC.Fps`、`PixelStreaming.GHSLowLatencyPlayout`。布尔命令行沿用 Epic 的 `true/false` 解析，**不能用 `=0` 代替 `=false`**。

不限帧时，硬件编码器的正帧率值只作为码率控制提示：初始化取有效 codec hint，无效时用 60，随后每 0.5 秒从实际提交帧采样。该提示不判断是否发送当前帧。不存在人为设置 120、300 或 999 充当“不限帧”。CPU/GPU、硬件编码器、浏览器、网络拥塞和 WebRTC 自身调度仍决定实际吞吐，不能据此保证任意帧率。

## 兼容和集成

- UE5.8 仍提供完整 Legacy PixelStreaming；项目的 `UPixelStreamingInput`、`SendPixelStreamingResponse` 和 `PixelStreaming.WebRTC.*` 名称继续保留。服务器和播放器协议不在本次补丁中改动。
- 保留 UE5.8 的 `CreateVideoSource(bool bInRequireUniqueId, ...)` 与 SFU 调用参数、按分辨率的 `GetLayer({ Width, Height })`、AVCodecs `MinQuality/MaxQuality` 字段、信令连接的弱生命周期守卫，以及服务器端口探测的 bool 返回值和 `Sockets` 依赖。
- 官方配置从 `BasePixelStreaming.ini` 更名为 `DefaultPixelStreaming.ini`；旧 AssetTypeActions 被新的 AssetDefinition 实现替代。未保留重复的旧文件。
- 在新基线上逐项保留原 13 个修改文件及 policy/回归测试两个新增源文件：项目插件资源定位和静态库链接、可选 RTP 帧率限制、采集 worker 生命周期、硬件帧率提示和低延迟 playout。与 UE5.8 的差异由 manifest 独立记录，不将整个旧插件覆盖新引擎 API。
- 前端 UE5.4 库的 `WebRTCFPS` 设置原最小值为 1，必须允许 0，避免 initialSettings 回写成 1 FPS。
- 本服务通过进程级命令行或 `PixelStreaming.WebRTC.Fps` 设置统一帧率；该路径同步现有视频 sender，并用于后续 peer 和 simulcast。单独调用某个 streamer 的 `SetStreamFPS(0)` 不会改写全局编码器策略，不是本补丁支持的独立不限帧入口。
- 0 FPS 强制 coupled，即使同时请求 decoupled；不在 0 上做除法。退出 decoupled 时唤醒并退出旧 worker。独立生命周期锁串行管理 worker，capture 回调用短锁保护事件指针；退出时先转移 runnable 所有权，释放短锁后等待线程，不持有 Tick 锁等待退出。
- `DisableFrameDropper` 没有默认打开；保留网络拥塞控制，避免用堆积排队换帧数。
- 编码器本身已经使用 `UltraLowLatency`，补丁没有再增加不存在的 NVENC CVar。
- `playout_delay=0/0` 是尽力而为的 RTP 提示，不保证浏览器立即显示，也可能降低高抖动链路的容错。需比较接收端 jitter buffer、冻结、丢帧、RTT 与画质。
- 编译资源路径使用项目插件 `PluginDirectory`；编辑器服务器资源通过 `IPluginManager` 找同名有效插件。
- 安装版引擎的 `WebRTC` 模块设置了预编译属性，其 `AddEngineThirdPartyPrivateStaticDependencies` 在 Editor 模块构建时不传递 LibVpx / OpenSSL / libOpus / zlib。项目版 PixelStreaming 明确依赖这些**引擎自带模块**，以解决重链接时的 `vpx_*`、`SSL_*`、`opus_*` 缺失；没有下载或替换库，也未硬编码第三方库绝对路径。

## 验证

在项目根目录执行：

```powershell
./Tools/PixelStreaming/engine-patch/run-policy-tests.ps1
./Tools/PixelStreaming/engine-patch/verify-patch.ps1 -EngineRoot D:/UE/UE_5.8
```

第一项用 MSVC 14.44 编译并运行实际 C++ policy 测试，覆盖已有 cap 清除、正数恢复、capture coupling、零/异常值、120 FPS 采样以及时间戳倒退。生成物只写 `.test-output` 并忽略。第二项比对所有源码和引擎基线哈希，并检查新引擎 API 和实际补丁集成点。迁移前该检查已以缺少 UE5.8 unique stream-id API 失败；刷新 manifest 本身不代表源码正确。

UE 自动化测试：`GHS.PixelStreaming.UncappedPolicy`。它使用真实 WebRTC `RtpEncodingParameters`、`EncodedImage` 和 `FVideoSourceGroup`，不启动服务器。必须在重新编译项目插件后的 Editor/Development 进程中运行，不能用旧引擎 DLL 代替。

并发回归测试：`GHS.PixelStreaming.ConcurrentCaptureModeSwitch`。在独立 capture 回调线程运行期间往返切换 120 / 0 FPS 共 200 次，覆盖事件触发、worker 停止和重新创建的生命周期。测试临时启用 fence，结束后恢复原值与设置优先级，不连接真实服务器。

结构测试和 policy 测试不能代替完整 Editor/Game 构建，以及服务器真实 WebRTC 帧率/延迟验证。由主任务统一执行构建与真实连接验证。

现有播放器仍固定为 `@epicgames-ps/lib-pixelstreamingfrontend-ue5.4@1.1.6`；其 SDP 补丁有精确 SHA256 防护，不能只改版本号就换 SDK。UE5.8 Legacy 信令字段和数据通道消息 ID 保持兼容形态，但需在新发行包实测握手、H264、鼠标/键盘、中文搜索响应、断开/重连、独立实例、0/60 FPS 和码率限制后才能声明端到端兼容。UE5.8 官方 AVCodecs 的 QP 到质量换算也应随真实编码画质一起核对。

修改补丁后先审查差异，再运行 `update-manifest.ps1` 刷新项目哈希；该脚本拒绝未经重新评估的引擎版本。不要把更新 manifest 当成测试通过。
