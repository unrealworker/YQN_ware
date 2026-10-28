# Windows 启动器

`build.ps1` 使用 Windows 随附的 .NET Framework C# 编译器，先运行真实进程和本机 HTTP 自检，再生成 `Deployment/GHSPixelStreaming/像素流服务启动器.exe`。无需安装 Node 或 .NET SDK；部署目录需同时包含打包游戏、`runtime/node.exe`、`server/server.js` 和网页资源。

```powershell
& .\Tools\PixelStreaming\launcher\build.ps1
& .\Deployment\GHSPixelStreaming\logs\GHSLauncher.Tests.exe .\Deployment\GHSPixelStreaming\logs\launcher-selftest.json
```

启动器也支持 `--self-test <JSON报告路径>` 和 `--gui-smoke <PNG路径>`。自检在系统临时目录创建独立夹具；不会启动真实仓库游戏。界面渲染检查在屏幕外创建测试窗口，不操作用户的其他窗口。

界面依据 `Design/GHS_Twin_SaaS_Concept/exports/current` 的启动器画板实现：深蓝 56px 标题栏、白色 12px 圆角卡片、左侧配置与右侧场景/运行状态、固定底部操作。实际 Windows DPI 下按比例布局；初始与最小尺寸都限制在鼠标所在屏幕的工作区，并在该区域居中。窗口缩小时配置区滚动，底部启动/停止始终可见。`Assets/warehouse-overview.png` 来自项目设计资产，编译时嵌入 EXE，不需要 WebView 或远程图片。预览是静态仓库图片。

端口检查直接标记冲突字段并禁用启动，修改后可重新检测；启动前再次校验。运行时配置控件统一禁用，端口显示“已监听”。运行卡片读取后端实际帧率与当前目标；尚无实际遥测时显示 `— / 目标`。高级参数提供 FPS 上限及最低/起始/最高码率，保留原有配置字段和校验规则。关闭本地程序窗口仍在后台渲染。在线访问者存在时，停止和关闭启动器均先确认；接入上限默认 10 人，可在访问设置中选择 1–10 人。达到上限后拒绝新访客，不替换已有连接；上限不是性能承诺。

新配置默认 `fps:0`，表示无固定帧率上限；也可设置 15–120 的固定上限，1–14 会在启动前被拒绝。旧配置明确保存的 FPS 保持原值。0 模式下独立实例排队启动，不按人数均分或降低目标帧率；实际速度仍取决于服务器与网络。实例和访问者的 `queued` 状态显示“排队中”。运行列表将目标 0 显示为“无固定上限”，实际测得 0 FPS 仍显示 `0.0`，无遥测显示 `—`。

新码率预设的最低 / 起始 / 最高值（Mbps）分别为：流畅优先 `1 / 8 / 24`、清晰优先 `1 / 10 / 35`、超清细节 `1 / 16 / 50`，新配置默认流畅优先。读取、显示或保存配置不会重新套用预设；只有用户切换画质档位才应用新值。旧配置未包含 `qualityProfile` 但保存过码率时，保留原数值并标为自定义，包括旧 `8 / 20 / 35`。组装脚本仅在交付目录尚无配置时写入新默认值，不覆盖已有访问码、网络地址或明确设置。

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
- HTTPS 接入方式为单选：原生 HTTPS、本机 HTTPS 反向代理、云负载均衡 HTTPS；HTTP 仅用于临时验证。证书路径相对部署目录解析，写入独立运行目录前转为绝对路径；防止拷贝目录后证书解析到错误位置。
- 云负载均衡 HTTPS 保存为 `externalTlsTermination:true`，仅允许公网 HTTPS 地址，与原生证书及 `trustProxy` 互斥。证书由 ALB 管理，服务器使用 HTTP 回源；保持 `trustProxy:false`，不会因此信任 `X-Forwarded-For`，在线用户来源地址可能是负载均衡地址。
- 云模式禁用一键公网防火墙配置。管理员应将网页端口限制为实际 ALB 回源来源；ALB 需保留公网 Host、支持 WebSocket。管理员控制接口与 UE 信令接口仍仅本机监听。网页 / 信令连通不代表 WebRTC 视频已连通，UDP / TURN 需单独验证。
- 从公网切回局域网时自动清除并禁用反向代理，避免局域网入口误绑定到 127.0.0.1。手动配置中的 LAN + trustProxy 组合也会被拒绝。TURN 地址在保存前检查协议、主机格式、端口及账号完整性。
- 部分实例失败时，顶部显示橙色“部分实例异常”与后端说明；`ready` 标记为“信令就绪”，不等同于浏览器已经解码首帧。
- 公网 IP、域名、证书及 TURN 服务由部署方配置；启动器不会自动申请这些服务。HTTP 公网地址只适合临时未加密验证。
- 10 用户 GUI smoke 是界面夹具，不能作为 10 路真实视频或公网连通性验证。自动测试覆盖配置往返、HTTPS/代理错误组合、TURN 校验、相对证书路径、认证断开载荷、选择稳定性和原有进程所有权。

### 云负载均衡入口设置

停止服务后，点击“公网与访问设置”，网络模式选“公网访问”，填写公网 HTTPS 域名及至少 12 位访问码。HTTPS 接入方式选“云负载均衡 HTTPS（ALB 等）”，本机证书与私钥会禁用且不写入运行配置。保存后，主界面显示“云负载均衡 HTTPS”，网页端口保持 ALB 后端实际端口（例如 8080），然后启动服务。回源来源地址和安全组由管理员按现有 ALB 配置管理，启动器不会自动改变这些规则。
