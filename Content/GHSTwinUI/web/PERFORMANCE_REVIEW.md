# P0/P1 前端性能自评 · 2026-10-21

本轮只修改本目录的 JavaScript 和测试。保留现有 HTML/CSS、图片、图表、320ms 页面过渡、输入焦点与滚动恢复；原生 420ms 侧栏滑动和 Browser 60Hz 由原生集成保持。本轮没有启动 Unreal 或浏览器，没有把 Node 控制器测试结果当成帧率收益。

## 实现

- `TwinModel.prepareSnapshot()` 在接收边界归一化设备/设施一次，创建共享数组、ID 索引和状态计数。列表、详情、告警引用、报告复用结果。
- 页面依赖比较发生在生成 HTML/SVG 之前。总览只依赖设备数量和状态分布；设备列表依赖当前页行、筛选结果、状态分布和两个列表总数；设备详情只依赖当前设备及当前详情页签。场景坐标、CAD 包围盒和技术地图名不触发业务 HTML 重建。
- 静态库存/订单页不响应设备遥测；告警引用图片与设备轨迹仍会响应关联设备变化。同一 CAD 实例元数据更新不新增返回栈。离开详情返回列表时读取最新快照。
- 聚焦输入框时继续缓存最新数据，失焦后刷新；不抢焦点、不重置滚动。过渡期间的数据更新仍合并到现有过渡。
- 隐藏面板继续接收最后快照和明确的选择/清选状态通知，但不归一化、不生成 HTML、不发详细报告；恢复显示只归一化最后快照并呈现最终业务状态。

## 原生接口

| 接口 | 调用约定 |
| --- | --- |
| `window.twinSetVisibility(false)` | 420ms 滑出完成后调用，避免停掉仍可见内容 |
| `window.twinSetVisibility(true)` | 滑入开始前调用，先恢复最新数据；重复调用不刷新 |
| `window.twinSetDiagnostics(bool)` | 关闭时取消待发报告并跳过诊断布局读数和透明度采样；开启时发一次当前报告 |
| `?diagnostics=0` / `?diagnostics=1` | 页面启动时关闭/开启详细诊断；缺省开启以兼容旧验收。正常原生 ready 后显式关闭，`-TwinDiagnostics` 验收显式开启 |
| `window.twinGetPerformance()` | 返回轻量计数副本：receivedSnapshots、normalizedSnapshots、htmlBuilds、domWrites、skippedRenders、hiddenSnapshots，以及 visible/diagnostics |

完整快照结构以及 twinReceive / twinSelect / twinClearSelection 不变。详细 report 仍保留所有旧字段，并增加 performance 计数。未变业务页面不生成 HTML；诊断关闭不改变页面动画时长。

## 验证

运行 `& 'C:/Program Files/nodejs/node.exe' --test Content/GHSTwinUI/web/tests/*.test.js`：44/44 通过，包含原 27 项及新增 17 项。首轮新增测试先得到 9 项预期失败，再实现优化；后续补充了输入失焦刷新、同 CAD 元数据、设备追溯与待发诊断取消覆盖。独立评审发现的两个 CAD 问题均先用测试复现失败，再修复：完整记录省略的可选字段会清除，同 kind/id/instanceIndex 的返回栈记录同步最新完整信息，栈长度保持不变。

另用真实 JS 控制器复现了原生隐藏改选的顺序问题：先恢复可见再 twinSelect 会保留旧详情 120ms。修复后的回归从原生 UpdateBrowserVisibility 源码读取发送顺序，重放“显式快照 → 恢复可见”，验证恢复首帧即为新设备/新 CAD 实例，CAD 返回栈只增加一层。这是原生发送契约检查与 JS 行为重放，不能替代 UE/CEF 实际执行验收。

实际 Node VM 控制器计数实验（设备页，diagnostics=0）：

| 操作 | 接收数 | 归一化次数 | HTML 生成次数 | DOM 写入次数 |
| --- | ---: | ---: | ---: | ---: |
| 连续 10 个相同业务快照 | 10 | 10 | 0 | 0 |
| 隐藏时连续 10 个变化快照 | 10 | 0 | 0 | 0 |
| 恢复显示 | 0 | 1 | 1 | 1 |

以上实验详细 report 数为 0。原有快速切页、退出/进入/idle 时序、滚动/焦点、减少动画、设备/物料选中、清选返回列表、图片路径和场景区域 ID 回归均通过。`git diff --check` 没有空白错误。

仍需由统一真实 CEF/Unreal 验证确认原生显隐通知时机、图片加载与几何布局，以及 1080p 本地/像素流的帧耗时。此处没有声称已达到稳定 60fps，也没有修改或覆盖冻结基准副本。

## 原生 HUD P1 整合自评

后续授权的原生改动仅位于 `Source/Test/GHSTwinHUDWidget.cpp/.h` 和独立 `Tests/GHSTwinHUDPerformanceTests.cpp`。SceneData 实现由另一 agent 负责，未在本工作范围修改。

- NativeConstruct 和 2 秒刷新通过 `Refresh(World,true)` 统一注册/组件处理，逐帧调用有预算的 `MaintainCache(128)`。推送使用 `BuildSnapshotIfChanged`，主动选择与恢复显示强制完整快照。
- 正常运行 ready 后关闭诊断；`-TwinDiagnostics` 保留 LastBrowserReport 和原日志。完全滑出后通知网页暂停；恢复时先排入最新快照，再解除网页暂停，避免先显示旧数据再刷新。主动选择负责自己的唯一显式快照，防止打开隐藏面板时重复压入 CAD 返回栈。
- Points、过滤、聚合、排序、标签文案、状态颜色和尺寸按 100ms 重建；SceneData revision、选择、过滤、图层、密度、跨远近阈值、视口/场景区域变化即时失效。
- 可见点逐帧 ResolvePoint、投影和插值，保留 6/16/32 上限与小规模逐帧避让；快速相机旋转/移动提前重新筛选可见点。GROUP 聚合中心按 100ms 更新，而实际设备与选中 CAD 使用每帧真实位置。
- 选中模型 8 角投影在 Tick 计算一次供避让和 Paint 复用；字体路径/描述和单位椭圆点缓存。未合并 Slate Layer，保留原绘制顺序、面板尺寸、opacity=1、BrowserFrameRate(60)。
- 新增 CPU trace scope：GHSTwinHUD_Tick、SceneRefresh、PushSnapshot、POICandidates、VisibleProjection、SelectedProjection、Paint。GetPOIReport 新增 performance 对象，含 candidateBuilds、projectionFrames、pointProjections、selectionProjections、candidateCount、browserActive、diagnostics、worldScans、snapshotSerializations；旧 labels/selectionStroke 字段保持。
- 两个原生 Automation Test 覆盖 100ms/事件失效策略，以及宽屏/600px 底部面板在滑出中保持更新、完全隐藏暂停、展开前恢复。尚未编译/执行这些 UE 测试，由统一构建与运行验收完成。

只读接口复核未发现阻断；仍必须在真实 UE 中确认快速旋转、密集 POI 避让、选中边框及 420ms 滑动外观。没有用源码检查或 Node 测试替代原生视觉/帧耗时验证。
