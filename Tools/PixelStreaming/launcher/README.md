# Windows 启动器

`build.ps1` 使用 Windows 随附的 .NET Framework C# 编译器，先运行真实进程和本机 HTTP 自检，再生成 `Deployment/GHSPixelStreaming/像素流服务启动器.exe`。无需安装 Node 或 .NET SDK；部署目录需同时包含打包游戏、`runtime/node.exe`、`server/server.js` 和网页资源。

```powershell
& .\Tools\PixelStreaming\launcher\build.ps1
& .\Deployment\GHSPixelStreaming\logs\GHSLauncher.Tests.exe .\Deployment\GHSPixelStreaming\logs\launcher-selftest.json
```

启动器也支持 `--self-test <JSON报告路径>` 和 `--gui-smoke <PNG路径>`。自检在系统临时目录创建独立夹具；不会启动真实仓库游戏。界面渲染检查在屏幕外创建测试窗口，不操作用户的其他窗口。

界面依据 `Design/GHS_Twin_SaaS_Concept/exports/current` 的启动器画板实现：深蓝 56px 标题栏、白色 12px 圆角卡片、左侧配置与右侧场景/运行状态、固定底部操作。实际 Windows DPI 下按比例布局；初始与最小尺寸都限制在鼠标所在屏幕的工作区，并在该区域居中。窗口缩小时配置区滚动，底部启动/停止始终可见。`Assets/warehouse-overview.png` 来自项目设计资产，编译时嵌入 EXE，不需要 WebView 或远程图片。预览是静态仓库图片。

端口检查直接标记冲突字段并禁用启动，修改后可重新检测；启动前再次校验。运行时配置控件统一禁用，端口显示“已监听”。运行卡片读取后端实际帧率与当前目标；尚无实际遥测时显示 `— / 目标`。高级参数提供 FPS 上限及最低/起始/最高码率，保留原有配置字段和校验规则。关闭本地程序窗口仍在后台渲染。在线访问者存在时，停止和关闭启动器均先确认；最大 3 人和第 4 人替换最早访问者的后端规则保持不变。

独立审查构建和界面检查：

```powershell
& .\Tools\PixelStreaming\launcher\build.ps1 -OutputRoot .\Saved\PixelStreaming\LauncherReview
& .\Saved\PixelStreaming\LauncherReview\像素流服务启动器.exe --gui-smoke .\Saved\PixelStreaming\UIReview\launcher-idle.png
```

GUI smoke 同时输出待启动、运行中、紧凑窗口、1080p/150% 工作区、高级参数、真实临时端口冲突、启动中、停止中、日志展开的 PNG 和 JSON 清单，并断言底部操作不越界。尺寸自检还覆盖 1366px 笔记本、4K/200% 与矮工作区。运行截图中的连接、地址、FPS 是明确的界面测试夹具，不代表真实 UE/浏览器联通或性能测试。`ServiceSession` 与进程作业的自动测试仍使用隔离 IPC 夹具验证启动、失败回滚、取消和清理。

配置保存在部署根 `launcher.config.json`。服务启动配置和不含令牌的控制信息位于本次独立 `sessions` 子目录，停止后回收；日志保留在 `logs`。控制令牌每次随机生成，仅通过子进程环境传入，不写入配置或日志。

Node 通过 `CreateProcessW(CREATE_SUSPENDED)` 创建，加入 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 作业后恢复。停止先调用受令牌保护的 loopback `/stop`，超时关闭本次 Job；不会按进程名查杀 UE/Node，也不触碰端口占用者。异常退出、关闭启动器和启动失败均回收自身进程树。

“配置内网访问”只在点击时请求 Windows 提权，运行部署根 `Enable-LanAccess.ps1`，参数为 `HttpPort` 和当前 `ApplicationPath`。启动器启动时不会自动弹出 UAC。

源码：`Core.cs` 配置/校验；`OwnedProcess.cs` Windows 进程所有权；`ServiceSession.cs` 生命周期/认证控制接口；`MainForm.cs` 界面；`LauncherTheme.cs` 原生圆角控件；`SelfTests.cs`/`BackendFixture.cs` 自动自检；`GuiSmoke.cs` 屏幕外界面检查。
