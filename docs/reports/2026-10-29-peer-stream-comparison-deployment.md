# Peer-stream 同机对比部署验收

2026-10-29，按用户要求在阿里云 `10.100.185.161` 部署 inveta/peer-stream，统一 1920×1080、60 FPS 目标及上限。

## 访问与配置

| 方案 | 入口 | 服务目录 |
| --- | --- | --- |
| 原方案 | https://warehouse-sim.iyunquna.com/ | `C:\YQN_WareHouse` |
| peer-stream | https://warehouse-sim.iyunquna.com/peer-stream/ | `C:\YQN_WareHouse\PeerStream` |

两边使用同一个当前 Shipping 程序、H264、1/8/24 Mbps 最小/起始/最大码率、balanced 编码质量、MAINTAIN_RESOLUTION、低延迟参数和 UDP 50000–50199。原方案 `adaptiveResourceBudget=false`，不会按人数自动降低帧率目标。代理入口与原入口共用10人上限；没有做10实例性能压测。

peer-stream 使用固定上游 `3bbf69e6f5c388874b483296d600b38c6762a241` 的原播放器 SDK 和 UE5 一对一信令核心，增加本项目部署与进程生命周期适配。没有部署上游任意命令执行管理页。原服务只代理精确列出的比较页/播放器/health/玩家 WebSocket，媒体仍由 WebRTC 传输。peer 8088 与原引擎信令8888仅监听127.0.0.1；原入口8080供既有HTTPS网关访问。

## 本地与远端验证

- 原服务回归及代理集成：109/109通过；peer服务、会话生命周期、部署/回滚：10/10通过。部署事务测试使用隔离文件夹；端口检查的测试替身仅存在于测试夹具，生产安装脚本没有绕过参数。
- Windows PowerShell 5.1 安装预检在服务器通过。ZIP SHA256与本地一致，安装保留未知配置字段、凭据和原应用，原配置及变更文件已备份。
- 本机浏览器通过固定域名实际连接peer，视频1920×1080、WebRTC/ICE connected、协商video/H264；点击主仓库POI后屋顶打开并出现内部设备标签，输入有效。
- 点击peer“结束连接”后没有自动重连；服务health显示users=0、instanceCount=0，再进入原入口进行验证，没有同时运行两个测试UE实例。
- 原入口实际收到1920×1080画面，首页可见；连接统计显示60 FPS上限、独立场景。原浏览器测试连接也已关闭。
- 最终服务器 `UE_PROCESSES=0`，两套信令服务运行；原配置width=1920、height=1080、fps=60、adaptiveResourceBudget=false、maxViewers=10。两套都可再次按需启动实例。

60 FPS是配置目标与上限，不代表服务器或网络能始终交付60帧。peer首帧后短时读数35/37 FPS，后续交互截图47 FPS，退出前34 FPS；原入口一次读数24.9 FPS、7.83 Mbps、13ms RTT、188ms缓冲、1.27ms解码、21.34%区间丢包。这些不是同状态、同前台条件的持续基准：验证期间浏览器窗口曾被最小化，且两方案采样时间与屋顶状态不同，因此不能据此宣布peer更快，也不能排定GPU/网络的瓶颈占比。用户自行对比应保持浏览器前台、相同首页闭屋顶状态、同一客户端和网络，逐个入口测试并等待旧实例回收。

## 版本与回滚

- 部署代码：`master / a8e65f0`，新增同域名peer-stream对比部署并统一1080p60。
- 原应用清单sourceCommit保持 `449b86297487d9908136f3b728406e856c4f0adc`；地图SHA256保持 `1a28e3301d524bbb9aa0a32556e684d1468d4c7f095544e8a3430599e5a5aa01`。
- 对比文件清单新增peerComparison，sourceDirty=false、applicationUnchanged=true。
- 本地交付ZIP：`Saved/PeerComparison20261029/PeerComparison-a8e65f0.zip`，98464字节，SHA256 `d5b46dd9d921a93933634c3d86c21e603a19056524f5b53dca7b417bca30e66d`。
- 服务器解包目录：`C:\YQN_PeerComparison_a8e65f0`。
- 服务器备份目录：`C:\YQN_WareHouse\_updates\PeerComparison-20261029-121034-6072994bbe02480c8b8b01615a450d6c`。

回滚先在原控制台停止原服务，运行peer的Stop.cmd并确认退出，然后在该备份目录运行Rollback-PeerComparison.ps1，指定Target和Backup。脚本会恢复原配置/服务/清单，归档整个PeerStream目录；检测到用户后来修改过的文件会停止，避免覆盖。回滚保留旧配置1280×720/fps0；如只想停用比较入口而仍保留1080p60，可停止peer并将server/peer-comparison.json的enabled改为false，再重启原服务。

## 使用边界

原控制台的用户列表和 `/health.viewerCount` 只列原方案；peer使用自己的Status.cmd查看连接。两边经固定域名的接入名额仍合计限制10。开启原控制台安全访问保护后比较入口会关闭，避免绕过访问验证。原方案关闭/重启时其代理入口也会短暂不可用。

peer实例退出后约8–9秒回收。对比时先关闭另一入口的浏览器标签页，或点击peer“结束连接”，等待约10秒再切换。原控制台负责原服务，PeerStream/Start.cmd与Stop.cmd负责比较服务；本次没有新增开机任务或系统服务。

证据存放于忽略目录 `Saved/PeerComparison20261029/`：`remote-install-result.png`、`remote-final-config.png`、`peer-first-frame.png`、`peer-roof-open.png`、`peer-video-evidence.json`、`peer-release-evidence.json`、`original-first-frame.png`、`original-video-evidence.json`。安装过程没有重打包或修改UE场景。
