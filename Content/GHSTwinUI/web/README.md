# GHS 仓库业务面板

供当前项目 `SWebBrowser` 加载的离线 UI。入口为 `index.html`，不依赖网络、npm、构建服务或远程字体。

## 已实现

- 总览：库存容量环图、出入库完成比例、场景设备状态条形图。
- 库存：区域容量、48 格示例货位矩阵、物料搜索、空位/占用/锁定筛选、物料详情。
- 订单：入库/出库切换、累计趋势、状态筛选、完整演示队列分页、订单详情及设备定位。
- 设备：场景实时快照优先，作业设备/设施切换，图片列表，类型/状态/搜索/分页，模型大图、状态和任务详情。
- 告警：明确为演示的 7 条队列、分级、确认、详情和关联设备。确认不等于恢复；不下发设备控制。
- 追溯：示例物料事件；设备历史未接入时保持空状态，仅提供当前位置定位。
- 场景：全仓/俯视/两个月台预设，货架/设备/POI 图层，标签密度。
- 实际 CAD 货架和物料实例显示 CAD ID、实例序号及层/列（如果提供）。业务库存未绑定时不显示虚构 SKU/数量，可独立打开批准设计的演示物料。

## 数据与桥接

`window.twinReceive(snapshot)` 接收场景快照，设备数组存在即优先使用，包括空数组。`unknown`、不可用遥测和缺失比例显示“未接入 / —”，不冒充运行或 0%。库存、订单、物料、追溯和告警示例使用 `2026-10-20 14:20:08` 设计快照，页面标注演示。

向原生调用 `window.ue.twin.command(JSON.stringify(payload))`，动作：`ready`、`select`、`focus`、`clear`、`overview`、`preset`、`layers`、`poiDensity`、`report`。ready 在桥接尚未绑定时最多重试 10 秒。

原生可调用 `twinNavigate(page)`（`settings` 与 `scene` 均可）、`twinBack()`、`twinFilterType(type)` 和 `twinSearch(text)`。显式点选使用 `twinSelect(snapshot)`，即使对象 ID 不变也重新打开详情；周期更新继续使用 `twinReceive(snapshot)`，不会把用户返回关闭的详情重新打开。原生清空场景选择后调用 `twinClearSelection()`，清掉全部详情和返回栈，保留当前业务页筛选与滚动；它不回发 clear 命令。普通 `twinBack()` 仍逐级返回。设备类型为 `agv/forklift/stacker/truck/charger`。

渲染后 `report` 提交当前页面、详情、设备/设施数量、面板视口、水平溢出、图片失败和图表数量，供真实 CEF 自动化验证。

## 视觉与自适应

遵循批准的 `Design/GHS_Twin_SaaS_Concept/exports/visual-v4` 与 taste-skill app-screen 规则，保留用户指定白色面板、灰蓝文字、蓝色数据、四张紧凑指标卡。未重新抽取随机风格。设备模型图来自现有项目渲染，均注明模型预览。货架区域与地堆区域分别使用设计中的 warehouse-racks 与 warehouse-storage 场景图。视角预设为 overview（全仓）、top（俯视）、racks（货架区域）、floor（地堆区域）；缩略图为场景参考，不是实时摄像头。

56px 导航 + 业务面板；宽度低于 440px 缩小间距，低于 360px 导航折为顶栏；宽面板提高并列信息密度。内容在面板内滚动，图表使用 SVG 自适应视口。页面切换使用 120ms 旧页淡出 + 200ms 新页淡入，旧内容保留到退出完成后才替换。周期快照在过渡期间合并，连续导航以最后一次目的地为准；透明度过渡保持底部固定动作的位置稳定。减少动态效果时立即切换，切换中更改该偏好也会安全结束过渡。详情返回保留列表筛选、分页、滚动与搜索焦点；翻页在旧页退出后回到顶部。

## 检查

运行 `node --test Content/GHSTwinUI/web/tests/*.test.js`。当前 27 项通过：数量守恒、订单状态、库存分布、真实设备替换示例、未知遥测、查询分页、返回上下文、趋势时间间距、七导航和桥接、CAD 选择、焦点与刷新、主动再次点击同一对象和后台刷新之间的区别、全局物料搜索的明确演示路径、高 DPI 分数像素诊断，业务页面不显示内部地图名，以及真实过渡期间旧内容保留、周期刷新合并、相同快照不替换 DOM、快速连续切换、焦点/滚动恢复、减少动态效果及入场中切换偏好不重置滚动、分页时机和区域视角命令。

浏览器渲染验证以 Unreal 内实际 CEF 截图和 `report` 为准。1920×1080、1366×768、600×900 三个窗口已检查实际面板，七页无水平溢出或图片失败；600 底部面板采用横向七导航，设备动作固定可见。三轮视觉评审见 `docs/GHS_TwinUI_TasteReview.md`。独立 taste inspector 的 Edge 启动在本机提前退出，未将静态/VM 测试当作浏览器视觉验证。

## 素材

`assets/agv.png`、`truck.png`、`forklift.png`、`stacker.png`、`charger.png` 复制自设计 `assets/visual-v4`；仓库图来自设计现有场景导出。DroidSansFallback 来自项目原 HUD，Apache-2.0，许可见 `assets/FONT-LICENSE.txt`。

本轮过渡与区域预设修改通过 taste-skill 静态检查（0 fail）；唯一提示为真实货位编号的两位补零，保留。过渡仅作用于透明度，不移动固定操作栏；区域图片已逐张核对为对应的货架与地堆场景。新过渡的真实 CEF 动态观感仍由原生联调复验。

诊断报告的 transition.recentPhases 保留当前导航的 out / in / idle 实际经过阶段（快速中断时最多 8 项），记录 performance.now() 的 atMs、当时计算 opacity、可见/目标视图和序号。周期快照保留该历史，下一次独立导航重置；此记录供 CEF 验收，不控制视觉行为。
