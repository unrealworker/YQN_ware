# GHS 仓库业务面板

供当前项目 `SWebBrowser` 加载的离线 UI。入口为 `index.html`，不依赖网络、npm、构建服务或远程字体。

## 已实现

- 总览：核验库存数量、货主/SKU 数及叉车管理台账；订单进度与告警仍明确标注演示。
- 库存：337,783 现存、336,006 可用、55 冻结、1,722 分配、0 待移出；10 个区域主数据、5 条已提供样例及样例 ID 搜索。数量单位、真实容量/占用/空位/锁定位和场景映射待确认。原库容图与 48 格货位示意按用户要求保留，独立标注“数据未核验”。
- 订单：入库/出库切换、累计趋势、状态筛选、完整演示队列分页、订单详情及设备定位。
- 设备：默认显示 82 条叉车台账统计（62 正常、20 禁用、0 维修中）、五类分布及 5 条已提供样例；这些是管理状态，不代表设备在线/离线。独立“场景模型”页签保留作业设备/设施、类型/状态/搜索/分页、模型预览和定位。
- 告警：明确为演示的 7 条队列、分级、确认、详情和关联设备。确认不等于恢复；不下发设备控制。
- 追溯：先按仓库当地时间选择至少一小时的时段，再选择测试订单；由 Unreal 回放 5 台人工叉车、3 台装卸卡车的取货、装车、故障和离场过程。支持暂停、跳转、倍率、跟随、轨迹和关键事件；退出前确认并恢复原场景。尚未接入真实订单或设备历史。
- 场景：全仓/俯视/货架区域/地堆区域预设，建筑外壳/货架与货物/作业设备/POI 四个图层，标签密度，以及货架库容和地堆库容滑动条。库容只调整场景展示，不修改业务库存。
- 实际 CAD 货架和物料实例显示 CAD ID、实例序号及层/列（如果提供）。业务库存未绑定时不显示虚构 SKU/数量，可独立打开批准设计的演示物料。

## 数据与桥接

`business-data.js` 是库存与台账核验摘录的唯一数据源，含原问卷 SHA256、单元格来源、范围与时间。数据来自用户填写的 2026-10-22 问卷，不是生产接口；页面不自动刷新业务数据。库存查询时间 2026-10-22 22:27 UTC+08:00，最大 ETL 22:01:21；叉车只确认核验日期与自身来源/ETL 时间，不能沿用库存查询时刻。库存数量不擅自标为件/箱/托，不把样例或引用货位计为完整清单。

未核验部分沿用原 `TwinModel.demo`，总览保留原库存容量饼图，库存保留原容量、分区及货位矩阵。模块标注“数据未核验”；示例不填入核验数据源的未知字段。`inventoryDemo` 拥有独立筛选状态，与真实样例搜索互不污染。示例物料、订单、告警与场景演示同样标注未核验。

`window.twinReceive(snapshot)` 只更新场景快照，设备数组存在即优先使用，包括空数组。`unknown`、不可用遥测和缺失比例显示“未接入 / —”，不冒充运行或 0%。真实台账与场景 ID 没有已确认映射，台账不下发 `select/focus`。订单、独立演示物料和告警继续使用明确标注的 `2026-10-20 14:20:08` 演示数据。追溯使用独立的相对时间测试数据，按所选区间映射时间，不代表该时段的真实历史。

向原生调用 `window.ue.twin.command(JSON.stringify(payload))`，常规动作包括 `ready`、`navigate`、`select`、`focus`、`clear`、`overview`、`preset`、`openWarehouse`、`layers`、`capacity`、`poiDensity`、`settingsReset` 和 `report`。ready 在桥接尚未绑定时最多重试 10 秒。追溯专用协议见下节。

原生可调用 `twinNavigate(page)`（`settings` 与 `scene` 均可）、`twinBack()`、`twinFilterType(type)` 和 `twinSearch(text)`。显式点选使用 `twinSelect(snapshot)`，即使对象 ID 不变也重新打开详情；周期更新继续使用 `twinReceive(snapshot)`，不会把用户返回关闭的详情重新打开。原生清空场景选择后调用 `twinClearSelection()`，清掉全部详情和返回栈，保留当前业务页筛选与滚动；它不回发 clear 命令。普通 `twinBack()` 仍逐级返回。设备类型为 `agv/forklift/stacker/truck/charger`。

原生顶部搜索仍查询场景目录。页面内搜索仅查询已提供样例；旧版 `twinSearch` Web API 可匹配核验样例但不代表原生顶部搜索已接入业务明细。

开启 TwinDiagnostics 后，渲染 `report` 提交当前页面、详情、设备/设施数量、面板视口、水平溢出、图片失败和图表数量；`business` 包含来源模式、实际页面文本及 DOM 样例行数，供真实 CEF 验证。

## 订单测试回放

`replay-core.js` 负责时区、校验和命令时序；`replay.js` / `replay.css` 提供业务面板内的区间查询、订单列表、设备列表、事件列表和退出确认。设备或物料详情里的追溯入口进入同一查询页，不再展示旧版伪物料时间线，也不声称已关联该对象的真实轨迹。

区间按 `America/Los_Angeles` 解释，起止时间转换为 UTC 后必须相差至少 3,600 秒。夏令时切换造成的不存在时间直接拒绝，重复时间必须明确选择 PDT 或 PST。任意合法区间索引出相同的四个测试订单 `TEST-OUT-001` 至 `TEST-OUT-004`；选择任意订单均使用 `Content/GHSTwinUI/data/order-replay.json` 的同一组相对时间设备、路径和事件，循环至区间终点。页面始终标明“测试订单 / 测试回放”。

底部时间轴由独立透明页面 `replay-overlay.html` / `replay-overlay.js` 承载，放在 Unreal 场景区域底部的 168 设计像素高画布内，不占用业务面板。原生通过 `window.twinSetViewport(width, height)` 同步尺寸和 DPI。它提供播放/暂停、前后跳转 30 秒、1–64 倍速度、时间轴、设备跟随、全部/选中/关闭轨迹及回放全景。拖动时间轴先暂停，松开或失焦时只提交一次跳转，并按拖动前状态决定是否继续播放；到区间终点停住，可从头回放。

Unreal 是播放时钟、设备运动、装载动作和场景隔离的唯一执行方。开始回放时保存原场景状态，打开屋顶并临时隐藏、停用原场景设备（包括充电设施）；结束后恢复设备、图层、手动隐藏状态、屋顶和相机。网页仅显示原生状态、发送操作，独立浏览器预览不模拟 Unreal 设备运动。

主面板和透明时间轴均发送 `replayReady`，原生向两端调用 `window.twinReplayReceive(state)`。透明时间轴不发送普通 `ready`。命令均使用上文的 `window.ue.twin.command`：

| 动作 | 参数与用途 |
| --- | --- |
| `replayStart` | `orderId`、`startUtc`、`endUtc`；时间为 ISO 8601 UTC 字符串 |
| `replayPlay` / `replayPause` | 继续 / 暂停 |
| `replaySeek` | `time`：相对区间起点的秒数 |
| `replayRate` | `rate`：1、2、4、8、16、32、64 |
| `replaySelect` / `replayFollow` | `id`：选择 / 跟随设备；跟随传空字符串恢复自由视角 |
| `replayTrails` | `mode`：`all`、`selected` 或 `off` |
| `replayOverview` | 解除跟随并查看全部回放设备，不结束回放 |
| `replayEvents` | `start`、`end`：查看事件窗口；或 `reset: true` 返回当前时段 |
| `replayEndRequest` | 请求手动结束，显示确认弹窗 |
| `replayLeave` | `token`、`title`：保存网页内部操作，确认恢复后再执行 |
| `replayExitConfirm` / `replayExitCancel` | 确认结束并继续原操作 / 取消离开 |

状态包含 `active`、`preparing`、`playing`、`completed`、`time`、`duration`、`rate`、`startUtc`、`endUtc`、`orderId`、`isTest`、`followId`、`selectedId`、`trailMode`、`cycleDuration`、`error`，以及 `devices`、`events`、`markers`、可选的 `eventsWindow`。设备显示字段为 `id/type/title/state/loaded/visible/trip/load/capacity`；运动字段 `position/yaw/lift` 不参与整页重绘键，避免周期状态造成 DOM 重建或焦点丢失。

长区间关键事件按时间段聚合，标记保留实际 `count`、`rangeStart` 和 `rangeEnd`。点击聚合标记依次暂停、跳转到代表时间、选中关联设备并请求事件窗口；主面板自动切到关键事件，可查看后续或返回当前时段。原生每次最多返回 100 条事件、96 个聚合标记；时间轴进一步按像素间距合并，最多绘制 80 个标记，不为长区间无限增加 DOM 或场景设备。

离开由原生统一守卫。`navigate/select/focus/overview/preset` 等操作在回放中只请求退出，不先切页或移动相机；原生确认恢复后继续原操作。网页内部详情、返回、物料/设备追溯入口和重新选择时段使用唯一 `replayLeave.token` 保留目标参数，收到 `window.twinReplayContinue(token)` 后仅执行一次。确认时原生先发送 `active: false` 再发继续回调；取消时通过 `exitPending: false` 清理待执行操作并恢复原播放/暂停状态。弹窗文案来自 `exitTitle` / `exitActionLabel`，期间时间轴与场景操作锁定。

## 视觉与自适应

以 `Design/GHS_Twin_SaaS_Concept/Saas.pen` 和 `exports/current` 为当前设计，保留白色面板、灰蓝文字、蓝色数据和紧凑指标卡。设备模型图来自现有项目渲染，均注明模型预览。货架区域与地堆区域分别使用 warehouse-racks 与 warehouse-storage 场景图。视角预设为 overview（全仓）、top（俯视）、racks（货架区域）、floor（地堆区域）；缩略图为场景参考，不是实时摄像头。

56px 导航 + 业务面板；宽度低于 440px 缩小间距，低于 360px 导航折为顶栏；宽面板提高并列信息密度。内容在面板内滚动，图表使用 SVG 自适应视口。页面切换使用 120ms 旧页淡出 + 200ms 新页淡入，旧内容保留到退出完成后才替换。周期快照在过渡期间合并，连续导航以最后一次目的地为准；透明度过渡保持底部固定动作的位置稳定。减少动态效果时立即切换，切换中更改该偏好也会安全结束过渡。详情返回保留列表筛选、分页、滚动与搜索焦点；翻页在旧页退出后回到顶部。

## 检查

运行 `node --test Content/GHSTwinUI/web/tests/*.test.js`。覆盖核验数量对账、负值与缺失值、台账管理状态、样例与全量边界、来源时间、场景快照隔离，以及桥接、CAD 选择、分页/过滤、过渡、焦点/滚动、DPI 与弹出筛选行为。追溯测试还覆盖最小时长、夏令时、固定测试订单、拖动/失焦提交、离开确认、一次性继续回调、事件聚合及有界事件窗口。

实际 CEF 业务验证脚本为 `Scripts/ghs/verify_confirmed_business_runtime.py`，报告输出到 `Saved/ConfirmedBusiness/runtime.json`。追溯的原生运动、取放托盘、跳转确定性、设备池、退出恢复与性能验证使用 `Scripts/ghs/verify_order_replay_runtime.py`，在独立的 `-game -RenderOffscreen -TwinDiagnostics` 进程内运行，证据输出到 `Saved/OrderReplay/Runtime/verification.json` 及同目录截图；脚本不改编辑器世界或保存地图。网页协议/DOM 测试和独立浏览器预览不能替代这项 Unreal 运行时验证。

浏览器渲染验证以 Unreal 内实际 CEF 截图和 `report` 为准。1920×1080、1366×768、600×900 三个窗口已检查实际面板，七页无水平溢出或图片失败；600 底部面板采用横向七导航，设备动作固定可见。三轮视觉评审见 `docs/GHS_TwinUI_TasteReview.md`。独立 taste inspector 的 Edge 启动在本机提前退出，未将静态/VM 测试当作浏览器视觉验证。

## 素材

`assets/agv.png`、`truck.png`、`forklift.png`、`stacker.png`、`charger.png` 复制自设计 `assets/visual-v4`；仓库图来自设计现有场景导出。DroidSansFallback 来自项目原 HUD，Apache-2.0，许可见 `assets/FONT-LICENSE.txt`。

本轮过渡与区域预设修改通过 taste-skill 静态检查（0 fail）；唯一提示为真实货位编号的两位补零，保留。过渡仅作用于透明度，不移动固定操作栏；区域图片已逐张核对为对应的货架与地堆场景。新过渡的真实 CEF 动态观感仍由原生联调复验。

诊断报告的 transition.recentPhases 保留当前导航的 out / in / idle 实际经过阶段（快速中断时最多 8 项），记录 performance.now() 的 atMs、当时计算 opacity、可见/目标视图和序号。周期快照保留该历史，下一次独立导航重置；此记录供 CEF 验收，不控制视觉行为。
