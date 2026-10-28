# Windows 启动器

`build.ps1` 使用 Windows 随附的 .NET Framework C# 编译器，先运行真实进程和本机 HTTP 自检，再生成 `Deployment/GHSPixelStreaming/像素流服务启动器.exe`。无需安装 Node 或 .NET SDK；部署目录需同时包含打包游戏、`runtime/node.exe`、`server/server.js` 和网页资源。

```powershell
& .\Tools\PixelStreaming\launcher\build.ps1
& .\Deployment\GHSPixelStreaming\logs\GHSLauncher.Tests.exe .\Deployment\GHSPixelStreaming\logs\launcher-selftest.json
```

启动器也支持 `--self-test <JSON报告路径>` 和 `--gui-smoke <PNG路径>`。自检在系统临时目录创建独立夹具；不会启动真实仓库游戏。界面渲染检查在屏幕外创建测试窗口，不操作用户的其他窗口。

界面依据 `Design/GHS_Twin_SaaS_Concept/exports/current` 的启动器画板实现：深蓝 56px 标题栏、白色 12px 圆角卡片、左侧配置与右侧场景/运行状态、固定底部操作。实际 Windows DPI 下按比例布局；初始与最小尺寸都限制在鼠标所在屏幕的工作区，并在该区域居中。窗口缩小时配置区滚动，底部启动/停止始终可见。`Assets/warehouse-overview.png` 来自项目设计资产，编译时嵌入 EXE，不需要 WebView 或远程图片。预览是静态仓库图片。

端口检查直接标记冲突字段并禁用启动，修改后可重新检测；启动前再次校验。运行时配置控件统一禁用，端口显示“已监听”。运行卡片读取后端实际帧率与当前目标；尚无实际遥测时显示 `— / 目标`。高级参数提供 FPS 上限及最低/起始/最高码率，保留原有配置字段和校验规则。关闭本地程序窗口仍在后台渲染。在线访问者存在时，停止和关闭启动器均先确认；接入上限默认 10 人，可在访问设置中选择 1–10 人。达到上限后拒绝新访客，不替换已有连接；上限不是性能承诺。

独立审查构建和界面检查：

```powershell
& .\Tools\PixelStreaming\launcher\build.ps1 -OutputRoot .\Saved\PixelStreaming\LauncherReview
& .\Saved\PixelStreaming\LauncherReview\像素流服务启动器.exe --gui-smoke .\Saved\PixelStreaming\UIReview\launcher-idle.png
```

GUI smoke 同时输出待启动、运行中、紧凑窗口、1080p/150% 工作区、高级参数、真实临时端口冲突、启动中、停止中、日志展开的 PNG 和 JSON 清单，并断言底部操作不越界。尺寸自检还覆盖 1366px 笔记本、4K/200% 与矮工作区。运行截图中的连接、地址、FPS 是明确的界面测试夹具，不代表真实 UE/浏览器联通或性能测试。`ServiceSession` 与进程作业的自动测试仍使用隔离 IPC 夹具验证启动、失败回滚、取消和清理。

配置保存在部署根 `launcher.config.json`。服务启动配置和不含令牌的控制信息位于本次独立 `sessions` 子目录，停止后回收；日志保留在 `logs`。控制令牌每次随机生成，仅通过子进程环境传入，不写入配置或日志。

Node 通过 `CreateProcessW(CREATE_SUSPENDED)` 创建，加入 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 作业后恢复。停止先调用受令牌保护的 loopback `/stop`，超时关闭本次 Job；不会按进程名查杀 UE/Node，也不触碰端口占用者。异常退出、关闭启动器和启动失败均回收自身进程树。

“配置内网访问 / 配置公网防火墙”只在点击时请求 Windows 提权，按网络模式运行部署根 `Enable-LanAccess.ps1` 或 `Enable-PublicAccess.ps1`，参数为 `HttpPort`、当前 `ApplicationPath` 及必要的 `TrustProxy`。启动器启动时不会自动弹出 UAC。

源码：`Core.cs` 配置/校验；`OwnedProcess.cs` Windows 进程所有权；`ServiceSession.cs` 生命周期/认证控制接口；`MainForm.cs` 界面；`LauncherTheme.cs` 原生圆角控件；`SelfTests.cs`/`BackendFixture.cs` 自动自检；`GuiSmoke.cs` 屏幕外界面检查。


## 公网版本（2026-10-28）

- 控制台沿用深蓝标题、蓝色操作、白色卡片，并替换为最新闭合屋顶场景预览。
- 在线用户列表每秒从认证控制接口更新，显示名称、来源 IP、连接状态、在线时长。保持用户 ID 选择，不因刷新或排序变化误操作其他人；悬停可见浏览器与实例信息。
- “断开选中用户”二次确认，异步发送 `POST /disconnect {playerId}` 到仅本机的令牌保护接口；不会停止服务或其他用户。已断开用户必须显式重新进入。
- “公网与访问设置”包含网络模式、人数上限、公网地址、随机访问码、PEM 证书/私钥、本机 HTTPS 反向代理、STUN / TURN 地址和账号。保存后立即写入本机配置，服务运行时锁定。
- 本机配置含访问码及 TURN 密码，不属于分享文件；界面默认遮罩，运行列表和日志不显示这些凭据。生成访问码使用系统加密随机数。
- 原生 HTTPS 与本机 HTTPS 反向代理二选一。证书路径相对部署目录解析，写入独立运行目录前转为绝对路径；防止拷贝目录后证书解析到错误位置。
- 从公网切回局域网时自动清除并禁用反向代理，避免局域网入口误绑定到 127.0.0.1。手动配置中的 LAN + trustProxy 组合也会被拒绝。TURN 地址在保存前检查协议、主机格式、端口及账号完整性。
- 部分实例失败时，顶部显示橙色“部分实例异常”与后端说明；`ready` 标记为“信令就绪”，不等同于浏览器已经解码首帧。
- 公网 IP、域名、证书及 TURN 服务由部署方配置；启动器不会自动申请这些服务。HTTP 公网地址只适合临时未加密验证。
- 10 用户 GUI smoke 是界面夹具，不能作为 10 路真实视频或公网连通性验证。自动测试覆盖配置往返、HTTPS/代理错误组合、TURN 校验、相对证书路径、认证断开载荷、选择稳定性和原有进程所有权。
