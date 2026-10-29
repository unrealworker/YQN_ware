# GHS Peer Stream

使用 inveta/peer-stream 的原始播放器及 UE5 信令/一对一分配核心，与现有服务并行部署，供相同场景的交互对比。

## 使用

服务器目录为 `C:\YQN_WareHouse\PeerStream`，默认引用同目录树内当前 `App/Windows/Test/Binaries/Win64/TestGame-Win64-Shipping.exe`，不另带旧场景包。双击 `Start.cmd`；本机入口为 <http://127.0.0.1:8088/>。配置受限代理后，外部通过原域名的 `/peer-stream/` 访问。首次进入会在后台启动 UE；在网页内点击后操作鼠标键盘。双击 `Status.cmd` 查看用户与实例，双击 `Stop.cmd` 停止本服务以及本服务启动的 UE 进程树。

按本次对比要求，两套方案统一 1920×1080、60 FPS 目标，不按人数降低帧率。peer 默认 loopback 监听、H.264、独立视角、最多 10 个实例槽位；通过固定域名代理时，原入口与对比入口共用原服务的接入人数上限（当前 10 人），满员拒绝新增连接。直接连接 loopback peer 时保留上游等待队列。10 是配置上限，不是 GPU 承载能力结论；60 是配置目标，不保证实际接收帧率。代码仍支持显式 FPS 0，需依赖本项目已部署的 UE5.4 不限帧补丁。用户离开后空闲 8 秒回收，轮询可能再增加约 1 秒。

对比入口没有独立访问码；开启原服务的访问保护会禁用 `/peer-stream/`，避免绕过原入口保护。原入口的访问保护逻辑保持不变。

页面“结束连接”立即关闭当前 WebRTC 和信令并停止自动重连；点击“重新连接”才重新进入。对比时先结束另一方案的连接并等待实例回收，不要同时占用显卡。播放器布局、协议和源码体积不同，完整端到端效果应由同一客户端/场景/人数下的测试判断。

## 参数

先停止服务，编辑部署目录的 `settings.json`，再启动。

| 字段 | 用途 |
| --- | --- |
| executablePath | UE 启动 EXE，支持绝对路径或相对服务目录路径 |
| width / height | 渲染分辨率，默认 1920 / 1080 |
| fps | 默认 60，也支持 15–120 或显式 0 无固定上限；不按人数自动平分 |
| instances | 独立实例槽位上限，默认 10，可设置 1–10 |
| port | 网页与信令端口，默认 8088 |
| host | 默认 127.0.0.1；需要内网接入时改为 0.0.0.0 并配置防火墙 |
| minBitrateMbps / startBitrateMbps / maxBitrateMbps | 默认 1 / 8 / 24 Mbps，WebRTC 自适应码率 |
| qualityProfile | balanced / clear / ultra / custom，默认 balanced，与原方案使用同一 NVENC 预设与 QP 参数 |
| mediaMinPort / mediaMaxPort | 默认 UDP 50000 / 50199，与现有已开放范围一致 |
| idleTimeoutSeconds | 实例无用户后的保留时间，默认 8 秒 |
| startupTimeoutSeconds | UE 连接信令的超时，默认 120 秒 |
| iceServers | STUN/TURN 服务器数组，默认空，适用于本机测试 |

UE 使用 UDP 50000–50199。公网部署仍需要入口、HTTPS、ICE/STUN/TURN 与网络规则；本机首帧通过不代表公网已连通。两套 Node 服务可以常驻，实际 UE 进程只在连接时启动，独立占用可用 UDP 端口。可配置 `iceServers` 与原服务保持一致。若指定本项目的 `TestGame.exe` 启动壳且同包 Shipping EXE 存在，会直接管理后者，避免启动壳退出后丢失进程所有权。

服务带有自己的 Node 运行时，无需安装 npm。服务日志位于 `logs/`；允许日志输出的 UE 包还会生成 `ue-0.log` 等，关闭日志的 Shipping 包可能不生成此文件。`.state/control.json` 是本机控制凭证，启动时随机生成，不应分享。部署目录不纳入 Git。

## 上游及适配

上游：https://github.com/inveta/peer-stream

固定提交：`3bbf69e6f5c388874b483296d600b38c6762a241`。`upstream/` 保存原始文件及 SHA256 清单，MIT 许可见其 README。使用已有经 SHA512 校验的 ws 8.18.3。

`build.cjs` 保留上游信令消息、独立实例匹配、排队和浏览器 SDK；替换系统自启、任意命令执行、文件写入、按端口猜测 PID 的管理接口。`host.cjs` 仅通过参数数组启动指定 EXE，管理自有 ChildProcess，并提供固定静态文件入口；不会运行原版的 Boot/readline/exec-ue。停止接口仅允许本机且需随机令牌。网页增加部署状态、队列提示及实测接收帧率显示。此交付不包含上游原版管理页的任意脚本控制功能。

## 重建和验证

从项目根目录执行：

```powershell
node Tools/PeerStream/build.cjs --output Saved/PeerComparison20261029/PeerStreamBuild
node --test Tools/PeerStream/tests/*.test.cjs
```

重建会保留已有部署 `settings.json`，应先停止服务。测试默认从上述隔离构建目录取文件，也可通过 `GHS_PEER_TEST_BUILD` 指定测试目录。源代码在 `Tools/PeerStream`，独立于现有 `Tools/PixelStreaming`。实际视频验证需检查浏览器 `window.peerStreamMetrics`、首帧、画面内容和输入响应，不能仅以网页 HTTP 200 判断成功。公共 health 仅输出运行状态、人数和实例数量；详细 PID、玩家信息只在本地鉴权控制接口可见。

## 增量部署与回滚

`build-bundle.cjs` 从上述构建目录生成独立增量包；每次指定一个尚不存在的 Saved 子目录。包内只有服务代码、播放器、ws 依赖及安装脚本，不含 UE、Node 运行时、设置或凭据。先完成本地中文提交再生成最终包，可以在清单中记录准确的源版本。

```powershell
node Tools/PeerStream/build-bundle.cjs --output Saved/PeerComparison20261029/TransferBundle
```

在服务器停止两套流服务及其 UE 实例后运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-PeerComparison.ps1 -Target C:\YQN_WareHouse -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-PeerComparison.ps1 -Target C:\YQN_WareHouse
```

预检验证包内 SHA256、指定原服务版本、Node 与 UE 文件哈希，拒绝已存在的 PeerStream 目录和仍监听的服务。安装从服务器现有 runtime 复制 Node；读取当前 launcher.config.json，保留未知字段与凭据，仅统一 width/height/fps 为 1920/1080/60，关闭 adaptiveResourceBudget。Peer 配置沿用实际 UE、质量档位、码率、ICE 与人数上限，8 秒空闲回收。原应用和地图不变；交付清单增加比较服务文件哈希与独立来源记录。

安装输出备份路径及回滚命令。回滚同样支持 `-DryRun`，原文件与配置按备份逐字节恢复，新增 PeerStream 整目录移动到备份的 archive 中保留。检测到安装后手动修改过的受管文件会拒绝覆盖。脚本不会自动启动服务，操作者应先启动 PeerStream，再启动原服务代理并验证真实视频。
