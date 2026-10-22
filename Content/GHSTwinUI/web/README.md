# GHS 仓库业务面板

供当前项目 `SWebBrowser` 加载的离线 UI。入口为 `index.html`，不依赖网络、npm、构建服务或远程字体。

## 已实现

- 总览：核验库存数量、货主/SKU 数及叉车管理台账；订单进度与告警仍明确标注演示。
- 库存：337,783 现存、336,006 可用、55 冻结、1,722 分配、0 待移出；10 个区域主数据、5 条已提供样例及样例 ID 搜索。数量单位、真实容量/占用/空位/锁定位和场景映射待确认。原库容图与 48 格货位示意按用户要求保留，独立标注“数据未核验”。
- 订单：入库/出库切换、累计趋势、状态筛选、完整演示队列分页、订单详情及设备定位。
- 设备：默认显示 82 条叉车台账统计（62 正常、20 禁用、0 维修中）、五类分布及 5 条已提供样例；这些是管理状态，不代表设备在线/离线。独立“场景模型”页签保留作业设备/设施、类型/状态/搜索/分页、模型预览和定位。
- 告警：明确为演示的 7 条队列、分级、确认、详情和关联设备。确认不等于恢复；不下发设备控制。
- 追溯：示例物料事件；设备历史未接入时保持空状态，仅提供当前位置定位。
- 场景：全仓/俯视/两个月台预设，货架/设备/POI 图层，标签密度。
- 实际 CAD 货架和物料实例显示 CAD ID、实例序号及层/列（如果提供）。业务库存未绑定时不显示虚构 SKU/数量，可独立打开批准设计的演示物料。

## 数据与桥接

`business-data.js` 是库存与台账核验摘录的唯一数据源，含原问卷 SHA256、单元格来源、范围与时间。数据来自用户填写的 2026-10-22 问卷，不是生产接口；页面不自动刷新业务数据。库存查询时间 2026-10-22 22:27 UTC+08:00，最大 ETL 22:01:21；叉车只确认核验日期与自身来源/ETL 时间，不能沿用库存查询时刻。库存数量不擅自标为件/箱/托，不把样例或引用货位计为完整清单。

未核验部分沿用原 `TwinModel.demo`，总览保留原库存容量饼图，库存保留原容量、分区及货位矩阵。模块标注“数据未核验”；示例不填入核验数据源的未知字段。`inventoryDemo` 拥有独立筛选状态，与真实样例搜索互不污染。示例物料、订单、告警与场景演示同样标注未核验。

`window.twinReceive(snapshot)` 只更新场景快照，设备数组存在即优先使用，包括空数组。`unknown`、不可用遥测和缺失比例显示“未接入 / —”，不冒充运行或 0%。真实台账与场景 ID 没有已确认映射，台账不下发 `select/focus`。订单、独立演示物料、追溯和告警继续使用明确标注的 `2026-10-20 14:20:08` 演示数据。

向原生调用 `window.ue.twin.command(JSON.stringify(payload))`，动作：`ready`、`select`、`focus`、`clear`、`overview`、`preset`、`layers`、`poiDensity`、`report`。ready 在桥接尚未绑定时最多重试 10 秒。

原生可调用 `twinNavigate(page)`（`settings` 与 `scene` 均可）、`twinBack()`、`twinFilterType(type)` 和 `twinSearch(text)`。显式点选使用 `twinSelect(snapshot)`，即使对象 ID 不变也重新打开详情；周期更新继续使用 `twinReceive(snapshot)`，不会把用户返回关闭的详情重新打开。原生清空场景选择后调用 `twinClearSelection()`，清掉全部详情和返回栈，保留当前业务页筛选与滚动；它不回发 clear 命令。普通 `twinBack()` 仍逐级返回。设备类型为 `agv/forklift/stacker/truck/charger`。

原生顶部搜索仍查询场景目录。页面内搜索仅查询已提供样例；旧版 `twinSearch` Web API 可匹配核验样例但不代表原生顶部搜索已接入业务明细。

开启 TwinDiagnostics 后，渲染 `report` 提交当前页面、详情、设备/设施数量、面板视口、水平溢出、图片失败和图表数量；`business` 包含来源模式、实际页面文本及 DOM 样例行数，供真实 CEF 验证。

## 视觉与自适应

以 `Design/GHS_Twin_SaaS_Concept/Saas.pen` 和 `exports/current` 为当前设计，保留白色面板、灰蓝文字、蓝色数据和紧凑指标卡。设备模型图来自现有项目渲染，均注明模型预览。货架区域与地堆区域分别使用 warehouse-racks 与 warehouse-storage 场景图。视角预设为 overview（全仓）、top（俯视）、racks（货架区域）、floor（地堆区域）；缩略图为场景参考，不是实时摄像头。

56px 导航 + 业务面板；宽度低于 440px 缩小间距，低于 360px 导航折为顶栏；宽面板提高并列信息密度。内容在面板内滚动，图表使用 SVG 自适应视口。页面切换使用 120ms 旧页淡出 + 200ms 新页淡入，旧内容保留到退出完成后才替换。周期快照在过渡期间合并，连续导航以最后一次目的地为准；透明度过渡保持底部固定动作的位置稳定。减少动态效果时立即切换，切换中更改该偏好也会安全结束过渡。详情返回保留列表筛选、分页、滚动与搜索焦点；翻页在旧页退出后回到顶部。

## 检查

运行 `node --test Content/GHSTwinUI/web/tests/*.test.js`。覆盖核验数量对账、负值与缺失值、台账管理状态、样例与全量边界、来源时间、场景快照隔离，以及原有桥接、CAD 选择、分页/过滤、过渡、焦点/滚动、DPI 与弹出筛选行为。本轮实际 CEF 验证脚本为 `Scripts/ghs/verify_confirmed_business_runtime.py`，报告输出到 `Saved/ConfirmedBusiness/runtime.json`。

浏览器渲染验证以 Unreal 内实际 CEF 截图和 `report` 为准。1920×1080、1366×768、600×900 三个窗口已检查实际面板，七页无水平溢出或图片失败；600 底部面板采用横向七导航，设备动作固定可见。三轮视觉评审见 `docs/GHS_TwinUI_TasteReview.md`。独立 taste inspector 的 Edge 启动在本机提前退出，未将静态/VM 测试当作浏览器视觉验证。

## 素材

`assets/agv.png`、`truck.png`、`forklift.png`、`stacker.png`、`charger.png` 复制自设计 `assets/visual-v4`；仓库图来自设计现有场景导出。DroidSansFallback 来自项目原 HUD，Apache-2.0，许可见 `assets/FONT-LICENSE.txt`。

本轮过渡与区域预设修改通过 taste-skill 静态检查（0 fail）；唯一提示为真实货位编号的两位补零，保留。过渡仅作用于透明度，不移动固定操作栏；区域图片已逐张核对为对应的货架与地堆场景。新过渡的真实 CEF 动态观感仍由原生联调复验。

诊断报告的 transition.recentPhases 保留当前导航的 out / in / idle 实际经过阶段（快速中断时最多 8 项），记录 performance.now() 的 atMs、当时计算 opacity、可见/目标视图和序号。周期快照保留该历史，下一次独立导航重置；此记录供 CEF 验收，不控制视觉行为。
