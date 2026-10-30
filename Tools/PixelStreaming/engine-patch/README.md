# UE 5.8 PixelStreaming2 迁移说明

项目现在使用引擎安装目录中的 **PixelStreaming2**，不再构建项目 Legacy `PixelStreaming` 插件，也不修改引擎源码。这个目录保留名称仅为已有验证命令兼容；旧插件源码 manifest、无限帧率 policy 和补丁构建脚本已退役，不属于新发行包。

## 启动器设置和实际行为

| 设置 | 实际入口 | 行为 |
| --- | --- | --- |
| 异步采集（与渲染解耦） | `-PixelStreamingDecoupleFramerate=true/false` | PS2 原生独立采集时钟；不是 NVENC 原生异步编码开关。UE5.8 没有 `PixelStreamingEncoderAsync` 设置，不发送无效参数。 |
| NVIDIA 编码器 | `-PixelStreamingEncoder=NVIDIA` | 项目明确实现的别名，要求 NVIDIA RHI 与可用 NVENC API，只接受 H264/AV1；禁用软件 codec 协商。硬件不可用或发生软件回退时记录错误并退出，不能静默显示成功。 |
| 自动编码器 | `-PixelStreamingEncoder=Auto` | 保留 PS2 / AVCodecs 根据当前硬件选择编码器。 |
| 固定目标帧率 | `-FixedFPS=60` | 项目明确实现的别名，将 `t.MaxFPS` 与 `PixelStreaming2.WebRTC.Fps` 同步为 60，范围 5–120。不是固定模拟步长；不使用 `UseFixedTimeStep`，不让回放、交通时间随性能改变。实际能达到的帧率仍取决于硬件和网络。 |
| 关闭固定目标帧率 | 不传 `FixedFPS` | 由现有资源预算控制渲染帧率。PS2 协商 FPS 保留正数，不能把旧补丁的 FPS=0 语义搬进 EpicRtc。 |

引擎内部 CVar 前缀为 **`PixelStreaming2`**，命令行仍为 **`PixelStreaming`**：`UPixelStreaming2PluginSettings::GetCommandLineFromCVar` 会替换前缀并移除句点。例：`PixelStreaming2.WebRTC.Fps` 对应 `-PixelStreamingWebRTCFps=60`。

`GHSStreamingRuntime` 的 JSON 预算和每秒 metrics 继续使用：PS2 Min/MaxBitrate 变化由官方回调刷新 streamer；渲染预算只调整 `t.MaxFPS`，不临时破坏 RTP 协商的上限。固定目标开启时拒绝不同 FPS 的预算。metrics 增加 `streamingPlugin`、`encoderPolicy`、`nvencApiValidated`、`fixedTargetFps`、`decoupledCapture`，启动日志包含 `GHS_PS2_CONFIG`。NVENC API 检查仅说明驱动可用，实际编码、画质和客户端 FPS 还需要连接验证。

## 中文输入与响应

UE5.8 的 `UPixelStreaming2Input` 在 Internal 目录且没有导出供项目链接。项目通过公共 `IPixelStreaming2InputHandler` / `IPixelStreaming2Streamer` 实现 `UGHSStreamingInputComponent`，接收 `UIInteraction`，保留已有消息处理器，校验长度并按 UTF-16 解码中文搜索，使用官方 `Response` 消息回复浏览器。世界退出时恢复原处理器，模块延后准备或 streamer 重建时重新绑定。键鼠处理仍由官方 PS2 输入模块负责。

## 不继承的 Legacy 行为

- 旧 `GHSLowLatencyPlayout` 编码包私有字段补丁没有移植到 EpicRtc。PS2 保留官方低延迟编码和拥塞控制，不能宣称旧的 RTP `playout_delay=0/0` 仍存在。
- 旧 FPS=0 移除 RTP 上限的补丁不再存在。0 只可表示 `t.MaxFPS` 不限渲染，PS2 capture/encode FPS 必须为正数。
- Legacy 的并发 worker 测试不能证明 EpicRtc 正确，新版本需单独验证原生 decoupled 采集与真实连接。
- 不强制开启 frame dropper 旁路，也不通过固定模拟 delta 虚构 60 FPS。

## 验证入口

```powershell
./Tools/PixelStreaming/engine-patch/verify-patch.ps1 -EngineRoot D:/UE/UE_5.8
```

该命令只检查新插件启用、项目依赖以及所用公开 API / CVar，不能替代编译或流媒体验证。UE 自动化测试：`GHS.Streaming.Runtime.*`、`GHS.Streaming.PixelStreaming2.ValidatesLauncherOptions`、`GHS.Streaming.PixelStreaming2.ChineseUIInteraction`。预算测试请勿带 `FixedFPS`，因为固定目标会正确拒绝不同的预算帧率。

最终必须通过 Editor/Game 构建及实际浏览器测试：H264（默认）、1920×1080、60 FPS 目标、鼠标/键盘、中文搜索及响应、断开重连、独立实例、固定目标/解耦采集开关与实时码率预算。NVIDIA 模式要同时核对启动验证日志和客户端实际解码 codec；仅启动参数存在不算验证成功。
