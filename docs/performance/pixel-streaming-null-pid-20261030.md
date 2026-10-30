# 多实例排队导致启动器停止服务的修复记录

## 现场证据

2026-10-30 的远程部署验收中，首个客户端进入视频协商，其余客户端排队，随后所有客户端收到“服务已停止 / 启动器已停止服务”。主流程恢复远程桌面后核对到启动器日志：

- 08:21:36、08:21:37、08:21:38、08:21:39，连续四条“状态读取失败：无法将 null 转换为值类型。”
- 08:21:41，“本次服务和实例已停止。”

以上时间按现场启动器显示原样记录，不推断时区。此次 GPU 优化增量只替换 App，未替换启动器或服务端；这是多实例排队触发的既有协议兼容问题，不能据此判断 GPU 优化版本的渲染性能。

## 原因与修复范围

服务端尚未启动的排队实例没有进程，`/status` 正常返回 `pid: null`。启动器原先将 `InstanceStatus.pid` 定义为不可空的 `int`，.NET Framework 的 `JavaScriptSerializer` 因此拒绝反序列化整个状态。`MainForm.Poll()` 连续四次异常后调用停止流程，导致全部自有实例退出。

本地加载了与服务器旧交付清单一致的启动器程序集（SHA256 `3d3da91f9d997aee3e569f434652697f22a30c0e07088341312d11736f9f9a03`），使用 Windows PowerShell / .NET Framework 4 直接反序列化其真实 `ServiceStatus` 类型。`pid: null` 复现同样异常；数值 PID 成功。

最小修复：

- `InstanceStatus.pid` 改为 `int?`，保留服务端“未分配进程”的真实语义。
- 未分配 PID 的实例提示显示“PID 等待分配”；已分配 PID、状态颜色、FPS、布局保持原有行为。
- 不修改服务端、HTTP 超时、轮询重试次数或停止策略。

## 回归验证

新增两项测试：

1. 用真实混合状态 JSON（已启动实例为数值 PID、排队实例为 `null`）反序列化，并调用现有 `ApplyStatus`，验证排队提示和运行状态。
2. 启动隔离测试后端，通过经过认证的本地 HTTP `/status` 连续执行四次真实 `ServiceSession.ReadStatus()`，验证空 PID 不再导致状态解析失败，服务保持运行。测试不启动 UE，也不访问实际服务器。

先仅加入回归测试运行红灯：52 项通过、2 项失败，两项都因“无法将 null 转换为值类型”失败。随后实施最小修复，完整启动器自测 **54 项通过、0 项失败**，测试程序和 Windows 启动器均编译成功。

本地证据（不提交构建产物）：

- `Saved/GPUOptimization/LauncherNullPid/Red/logs/launcher-selftest.json`
- `Saved/GPUOptimization/LauncherNullPid/Green/logs/launcher-selftest.json`
- `Saved/GPUOptimization/LauncherNullPid/Green/logs/launcher-build.log`
- `Saved/GPUOptimization/LauncherNullPid/Green/像素流服务启动器.exe`

复验命令：

```powershell
pwsh.exe -NoProfile -File Tools/PixelStreaming/launcher/build.ps1 -OutputRoot Saved/GPUOptimization/LauncherNullPid/Green
```

本记录确认协议故障及本地回归结果；不把启动器修复等同于远程三路 1080p60 已验收。远程替换启动器后，仍需验证排队阶段、三个独立 UE PID 与同步客户端帧率。
