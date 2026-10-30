# UE 5.8 升级验证记录 · 2026-10-30

本轮按用户要求仅做本地功能验收，覆盖隔离副本的编译、真实渲染运行回归和资产保护，不包含服务器部署或服务器压力测试。Editor、Development Game、Shipping 打包均成功，本地单浏览器 Shipping 像素流及下述页面操作已实测连通。用户已接手后续验证，本轮停止额外测试；两路独立实例及完整浏览器追溯操作未完成，不标为通过。

## 版本、隔离与回退

| 项目 | 已核验内容 |
| --- | --- |
| 升级工作区 | `C:/Users/28109/.codex/worktrees/ue58-upgrade/Test` |
| 分支 / 本轮基线 | `codex/ue58-upgrade` / `2bc8d04808a8f38148407d22dcd1efa166ab438e`（接入 UE-MCP 并适配 UE5.4） |
| 目标引擎 | `D:/UE/UE_5.8`，UE **5.8.4**，Changelist **58902052**；项目 EngineAssociation 为 `5.8` |
| 日常打开 / 回退基线 | 后续 `D:/UEPro/Test` 使用 UE 5.8；升级分支经清洁状态检查后合入 `master`。UE 5.4 回退依据为 Git 基线 `2bc8d04` 和保留的 UE 5.4.4 引擎，不以原项目仍停留在 5.4 为前提 |
| 升级范围 | 保留 Legacy PixelStreaming 路线并适配 5.8 API；不是切换 PixelStreaming2。未因升级开启 Lumen 或光追 |
| 本机渲染环境 | Windows 11，i9-14900HX，32 GB 内存，RTX 5060 Laptop GPU，D3D12；不是阿里云服务器配置 |

后续日常打开使用 `D:/UE/UE_5.8`。如需回退，先保留现有改动，再在独立工作树取 Git 基线 `2bc8d04` 并使用已保留的 UE 5.4.4 引擎；不要通过重置当前工作区或把 5.8 保存后的资产反向覆盖来回退。此次内容校验确认资产未发生引擎保存转换。隔离与升级步骤见[执行计划](superpowers/plans/2026-10-30-ue58-upgrade.md)。

## 编译与原生测试

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| UE 5.4 原生基线 | 137 / 137 成功，测试报告 0 警告；NullRHI，仅逻辑基线 | [报告](../Saved/UE58Upgrade/ue54-native-baseline.json) |
| UE 5.8 Editor | `Result: Succeeded` | [最终增量日志](../Saved/UE58Upgrade/editor-build-mapdrag.log) |
| UE 5.8 Development Game | `Result: Succeeded`，产物 `Binaries/Win64/TestGame.exe` | [日志](../Saved/UE58Upgrade/game-development-build.log) |
| UE 5.8 Shipping 编译 / Cook / Stage / Archive | `ExitCode=0`，主场景打包完成；这不是运行或串流验收 | [打包结果](../Saved/PixelStreaming/Packaging/package-20261030-134559.result.json) / [日志](../Saved/UE58Upgrade/package-shipping-console.log) |
| UE 5.8 GHS 原生全组 | 138 项完成：137 成功 + 1 成功但带警告，0 失败 | [报告](../Saved/UE58Upgrade/Native/index.json) |
| IME 与 WorldSwitch 缓存隔离复跑 | 2 / 2 成功，测试报告 0 警告；包含上次出现警告的缓存用例 | [报告](../Saved/UE58Upgrade/IMEAndCache/index.json) |
| 当前视口 MapDrag | 1 / 1 成功，测试报告 0 警告 | [报告](../Saved/UE58Upgrade/MapDragCurrent/index.json) |

138 项全组中的唯一测试警告出现在 `GHS.Twin.Scene.Cache.WorldSwitchAndDestructionDetachDelegates`：RHICore 报告 **reserved resource allocated virtual size 258 GB 超过 256 GB 预算**。它描述资源预留虚拟地址大小，不能解读为占用 258 GB 物理显存或内存。该用例独立复跑无此测试警告；不把全组写成“零警告”。启动日志还记录 NVIDIA 驱动低于 610.00 时 TSR 16-bit VALU 被引擎禁用，因此“测试报告 0 警告”也不等于进程所有日志没有警告。

## 真实运行回归

以下 12 份报告均为 `success=true`，共 **117 个命名检查项、78 张捕获记录**；检查项数是报告 `checks` 数组长度，不是底层断言条数。它们在本机真实 UE Editor `-game` / CEF / RHI 环境串行运行，不是 NullRHI。运行入口和参数见[执行矩阵](../Saved/UE58Upgrade/runtime-matrix.json)与[串行执行器](../Saved/UE58Upgrade/run-runtime.ps1)。

| 脚本 | 检查项 | 主要覆盖 | 最终成功报告 |
| --- | ---: | --- | --- |
| `verify_ui_motion_runtime.py` | 16 | 总览、库存、订单、设备、告警、追溯、场景七页；hover / 点击高光、图表复用、面板隐藏恢复、窄屏 | [20261030_045323](../Saved/UIMotion/20261030_045323/runtime.json) |
| `verify_confirmed_business_runtime.py` | 9 | 已确认库存与设备台账、示例数据标记、说明提示、宽窄屏、场景标识与屋顶交互 | [AnnotationCleanup](../Saved/AnnotationCleanup/runtime.json) |
| `verify_roof_scan_runtime.py` | 12 | 默认闭顶、0.8 s 手动 / 0.5 s 快速打开、0.55 s 关闭、中途反向、最新定位胜出、内部禁选、POI 渐隐、空闲 Tick | [RoofScan](../Saved/RoofScan/runtime.json) |
| `verify_scene_capacity_runtime.py` | 21 | 四类图层控制、0 / 默认 80/100 / 100% 库容、设备与货物隐藏后禁选、实际屏幕射线、固定实例池、连续滑动、恢复状态 | [20261030_053536](../Saved/SceneControls/Runtime/20261030_053536/runtime.json) |
| `verify_order_replay_runtime.py` | 11 | 八台回放设备隔离、暂停 / 反向跳转 / 播放结束、测试订单、五种退出保护、场景还原 | [OrderReplay](../Saved/OrderReplay/Runtime/verification.json) |
| `verify_replay_visual_follow.py` | 11 | 待行驶轨迹裁剪、静止无轨迹、主题蓝 / 高度错开、POI、叉车跟随旋转缩放 / 禁平移、暂停同步特效 | [RemainingRoutes](../Saved/OrderReplay/RemainingRoutes/verification.json) |
| `verify_replay_smooth_turning.py` | 6 | 载货匀速转弯、确定性跳转、跟随持续、取放货与故障事件、循环固定池 | [SmoothTurning](../Saved/OrderReplay/SmoothTurning-20261026/runtime/verification.json) |
| `verify_replay_follow_panel.py` | 10 | 静止 / 移动叉车与卡车跟随下收展面板、中途反向、自由视角及还原 | [FollowPanel](../Saved/OrderReplay/FollowPanel-20261026/runtime/verification.json) |
| `verify_replay_panel_motion.py` | 9 | UE / CEF 面板收展同步、部分收起后反向、宽度断点、时间轴和场景还原 | [PanelMotion](../Saved/OrderReplay/PanelMotion-20261026/runtime/verification.json) |
| `verify_road_terminal_runtime.py` | 2 | 道路延伸与修正路口网格可见、路末车辆回收不增生 | [RoadTerminalFade](../Saved/RoadTerminalFade/Runtime/verification.json) |
| `verify_traffic_density_runtime.py` | 4 | 固定 32 实例 / 六方向、车辆运动、端点回收、业务标识不变 | [TrafficDensity](../Saved/TrafficDensity/runtime.json) |
| `verify_ui_motion_performance.py` | 6 | 22 个本地 CEF 采样场景；立即选中、快速切换最终目标、图表生命周期、隐藏后恢复 | [performance_ue58_20261030_050743](../Saved/UIMotion/performance_ue58_20261030_050743/performance.json) |

本轮修正了测试夹具与当前行为不一致的问题，没有为历史文案改写生产 UI：

- 库容旧断言把“没有设备标签”写成了“所有标签必须立即为空”。现在允许主仓库 `WAREHOUSE:GHS` 在开顶起始 **100 ms** 渐隐，过渡时不允许交互；闭顶 / 开顶未完成仍要求内部设备标签不可见、内部选择为空且不能穿顶选中。显式关闭 POI 开关仍要求标签全部消失，未通过全局过滤主 POI 来绕过该检查。
- 业务说明已从正文移入可访问的说明提示，测试改为同时核验可见内容、提示内容和数字动画到达目标。库存 **337,783 / 336,006 / 156 / 14,373**、设备台账 **82 / 62 / 20 / 0** 的已确认数值检查保留；示例库容的 **1,920 / 416 / 64、80.0%、2,400** 与未核验说明仍受检查。
- UE 5.8 GPU CSV 按实际 `GPUTime` 与有效 GPU pass 采样验证；不会把 Slate 回调间隔当作 GPU 用时，也不伪造旧版本缺失的 `GPU/Total` 列。

## 本机性能采样及边界

屋顶与库容均为固定 **1920 × 1080** 视口、`r.ScreenPercentage=100`、关闭动态分辨率 / VSync / FPS 上限的独立采样；每个状态约 10 秒。下面使用 RHI CSV 的 `GPUTime`，所有窗口 `gpu_verified=true`，P95 按保留全部帧的 nearest-rank 计算，未剔除尖峰。

| 场景窗口 | GPU 样本帧数 | GPU 均值 ms | GPU P95 ms |
| --- | ---: | ---: | ---: |
| 屋顶：预热后的闭合状态 | 1,080 | 8.760 | 10.281 |
| 屋顶：反复正常开合，完成 7 次打开 | 808 | 11.861 | 13.444 |
| 库容：货架 80% / 地堆 100% | 749 | 12.799 | 13.710 |
| 库容：货架 0% / 地堆 0% | 762 | 12.584 | 13.384 |
| 库容：货架 100% / 地堆 100% | 751 | 12.766 | 13.675 |
| 库容：CEF 连续滑动 | 741 | 13.243 | 14.181 |

屋顶打开会改变可见场景负载，背景交通也仍在运行；两个窗口的差值不能单独归因于溶解材质，更不是 5.4→5.8 的性能提升。反复开合窗口保留了 1 个 `FrameTime > 50 ms` 样本（最大 81.272 ms），同时 GPU 最大 15.072 ms；不宣称完全无卡顿。库容四个窗口的 GPU 和 FrameTime 均未记录超过 50 ms 的样本，但短样本不能替代长时间压力测试。

库容覆盖 25,056 货架库位、7,530 地堆组、13 个组件和 7 个共享材质。连续拖动期间初始化扫描仍为 1，未增长实例池；零库容仍保留货架钢结构。双蓝托盘地堆沿用现有资产与 LOD，未因本次迁移重建模型。

UI 性能记录来自本机 UE 内嵌 CEF 的 RAF / `performance.now()`，不是视频接收帧率：

| UI 采样 | RAF 均值 / P95 / 最大间隔 ms | 其他证据 |
| --- | --- | --- |
| 七页各两轮导航，共 14 次 | 16.664–16.666 / 16.7–16.8 / 16.8 | 首次 idle 232.1–248.3 ms；导航阶段真实 callback 最大 27.7 ms |
| 每 45 ms 快速导航 | 16.666 / 16.7 / 16.8 | 最终操作 272.6 ms，idle 504.8 ms，最终目标正确 |
| 同页变化数据快照 | 16.665 / 16.8 / 16.8 | 8 次数据更新，图表未重建；实际 callback 最大 25.1 ms |
| 原生隐藏再恢复面板 | 19.174 / 16.8 / **249.9** | 保留隐藏期间停帧；恢复后图表完成、无挂起任务，实际 callback 最大 258.1 ms |

22 个场景的 Long Tasks 记录为空，但不能用这一点否认回调延迟。JS 派发不包含操作系统鼠标延迟，RAF 也不完整代表合成器呈现；本报告不据此宣称服务器或远程用户稳定 60 FPS。

## 本地 Shipping 单浏览器验证

已通过真实浏览器连接本地 Shipping：单独实例 `viewer-a3777ea2ea23`，画面 **1920 × 1080**。已保存的[浏览器首帧统计](../Saved/UE58Upgrade/StreamingAcceptance/browser-first-frame.json)显示 `playing`、`firstFrame=true`、`viewerCount=1`、内网 UDP；该次统计为 **60.357 FPS、18.611 Mbps、丢包 0%、冻结次数 0**，解码均值 0.542 ms、缓冲 14.078 ms，首帧耗时 9,836 ms。它是单次观察，不是持续帧率保证。

同轮实际 `RTCPeerConnection.getStats()` 还确认接收编码为 `video/H264`、解码尺寸 1920×1080。此前播放器页面另一采样时刻约 58.65 FPS，与上述 JSON 不是同一次采样。没有据此推断两路并发或服务器性能。

| 实际操作 | 结果与截图 |
| --- | --- |
| 加载 Shipping 全景 | 已显示真实画面；[01 全景](../Saved/UE58Upgrade/StreamingAcceptance/01-shipping-overview.png) |
| 鼠标点击打开屋顶 | 已展开并显示内部；[02 屋顶打开](../Saved/UE58Upgrade/StreamingAcceptance/02-shipping-roof-open.png) |
| 输入中文“人工叉车”并点击 `FORK01` | 搜索显示 16 项结果，点击后成功定位；[03 中文搜索与定位](../Saved/UE58Upgrade/StreamingAcceptance/03-chinese-search-focus.png) |
| 切换追溯页面 | 页面已显示；[04 追溯页面](../Saved/UE58Upgrade/StreamingAcceptance/04-shipping-replay-index.png)。仅此操作，不等于完成浏览器内完整回放流程 |
| 刷新浏览器 | 恢复同一 `instanceId=viewer-a3777ea2ea23` 的会话 |

此前真实 UE 运行脚本已覆盖追溯、跟随、时间轴与退出保护，详见上表；这与尚未完成的完整浏览器操作属于不同证据范围。

## 资产保护与剩余验收

[内容哈希校验](../Saved/UE58Upgrade/content-after-verification.json)记录 **1,075 个 Content 文件（含 1,005 个 `.uasset` 和 12 个 `.umap`）** 与[升级前清单](../Saved/UE58Upgrade/content-before.csv)逐项一致，无新增、丢失或变更；总字节数 760,108,556。该次哈希校验时，原项目 `master` 受版本管理的工作区干净；这是迁移前保护记录，不代表原项目之后仍使用 5.4。运行与打包报告均确认主场景 SHA-256 不变：

`1a28e3301d524bbb9aa0a32556e684d1468d4c7f095544e8a3430599e5a5aa01`

屋顶报告另外核验了地图、屋顶网格、屋顶 / 细节材质及玻璃材质共 7 个文件前后哈希一致。上述内容资产结论不意味着源码或 Web UI 没有迁移改动，也不包括忽略的运行缓存。

按用户最新指令，停止额外测试，由用户接手本地两路独立实例、完整浏览器追溯流程及进一步使用验证。本轮单浏览器结果与此前 12 份真实 UE 运行回归均保留；尚未完成的两实例和完整浏览器追溯流程不写通过。服务器部署、服务器三实例及阿里云网络与资源测试不属于本轮验收要求。现有结果只覆盖本文列出的条件；此记录不是全部功能或所有设备的最终保证。
