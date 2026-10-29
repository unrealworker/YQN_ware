# 验证记录

## 对比部署适配（2026-10-29）

- 构建输出 `Saved/PeerComparison20261029/PeerStreamBuild`；原部署与 upstream 源文件未覆盖。
- 对比默认参数为1080p60，新增60FPS启动参数/公开health检查，保留FPS0兼容性；编码/码率/端口一致性、启动壳到Shipping进程所有权、代理子目录URL、主动退出与晚到回调保护测试，共7项通过。
- HTTP/本地鉴权控制集成测试通过；公共 health 不返回 PID、玩家列表、实例明细。
- Start/Stop/Status PowerShell 语法检查通过，控制操作通过同一 serviceId 匹配当前启动实例。
- 构建后播放器 SDK 与 upstream SHA256 均为 `85eb4ec5e9a7b8fdb3be92d89cb8d31f443e1dd7c76e750a1e90b92db03b895f`。
- 增量部署测试使用 Saved 下独立夹具，验证只读预检、安装、原配置未知字段与 ICE 凭据保留、1080p60、运行时本机复制、交付清单及地图哈希保留、逐字节回滚和新增目录归档；有效服务监听、预先存在的 PeerStream、被篡改的包均拒绝更新。
- 本机已有历史 PeerStream 占用 8088，不停止该进程。文件事务测试只在生成的夹具副本中替换端口探针为空；生产脚本没有绕过选项，实际端口保护另用原脚本验证。
- 以上仅为本地适配和协议验证，不代表服务器视频、并发或性能通过；远端真实验证由服务器部署验收记录单独给出。

## 历史本机验证（2026-10-28）

- 引擎程序：`D:\UEPro\Test\Package_Windows\Windows\TestGame.exe`。
- 固定上游提交：`3bbf69e6f5c388874b483296d600b38c6762a241`，原始播放器 SDK 未修改。
- 入口：`http://127.0.0.1:8088/`；独立实例模式，配置 2 槽位；本次只验证 1 个真实 UE 实例，没有并发压测。
- `node --test Tools/PeerStream/tests/host.test.cjs`：2 项通过，覆盖无效配置、公开文件边界、拒绝执行接口、拒绝远程执行器、控制令牌与正常停止。
- Windows PowerShell 5.1 启动、状态、停止脚本语法通过；Start 和 Stop 均实际运行。
- Chromium 浏览器真实 WebRTC 首帧通过，视频尺寸 1920×1080，RTCPeerConnection 为 connected，DataChannel 为 open。
- 浏览器点击主仓库 POI，屋顶消失并展示仓库内部，确认鼠标事件抵达 UE；截图在部署目录 `verification-interaction.png`。
- 停止时浏览器收到会话结束通知。首次在工具沙箱中运行时，Windows 拒绝 taskkill，服务保留 stop_failed 状态；核验进程所属后清理并改在正常 Windows 权限环境启动，复测 Stop 成功且 TestGame / Shipping 进程均已退出。
- 再次启动后真实首帧通过；一条接收统计样本为 1920×1080、61 FPS、171 个已解码帧、0 个丢帧。这是短时功能验证样本，不是持续性能或公网延迟结论。截图 `verification-ready.png`。
- 最终服务重新启动。`.state/`、日志、截图及运行时位于忽略的部署目录。
- 尚未验证公网、跨网络 TURN、两实例并发承载能力及移动端触控。

程序验证前后 SHA256 一致：

| 文件 | SHA256 |
| --- | --- |
| TestGame.exe | 004EE4E8BC81E73ED5535DF8AFBC32EC35CC8B5591494362A4B21E2F1040C30A |
| Test/Binaries/Win64/TestGame-Win64-Shipping.exe | 93CF7D70C8D8C75121B1E91B96EC0D6212DE3322BF845C36BCF8844AC1BAEC1A |

2026-10-28 历史验证时未提交；本次完成验证后按项目 AGENTS.md 自动创建中文本地提交。
