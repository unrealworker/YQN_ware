> 历史评审，已由 2026-10-21 当前设计替代。开发请以 [README](README.md)、[Saas.pen](Saas.pen) 和 [当前评审](taste-current-review.md) 为准。

# taste-skill 业务界面评审

日期：2026-10-20。对象：23 张 Pencil 桌面静态画板，最新导出为 archive/superseded-exports/business-v3/。

依据 [design-taste-frontend](C:/Users/28109/.agents/skills/design-taste-frontend/SKILL.md)、[app-screens](C:/Users/28109/.agents/skills/design-taste-frontend/references/app-screens.md) 和 [critique](C:/Users/28109/.agents/skills/design-taste-frontend/references/critique.md)。采用工作型应用界面的任务、数据、导航、列表、状态与层级准则，不套用营销网站的照片数量、hero 和页面动效条款。延续用户已确定的灰白空间、蓝色强调、白色侧栏及中文字体。

## 需求覆盖

值守人员先看库容、今日作业量和设备状态，再进入货位物料、订单、设备或事件。本轮补齐总览、库存、订单、设备、告警、追溯、场景七项入口；增加物料/订单详情、入库/充电设施切换、导航关系和边界状态。每项入口的具体内容见 README。保留此前 POI、HUD、聚合、悬停与轨迹页面。

## ROUND 1

Seen in one second: 灰白仓库旁是运营信息，总览首先呈现库容和今日出入库。
Idea (one sentence): 空间中的货位、物料与设备成为业务查询入口，侧栏继续完成判断与定位。
Live thing: 搜索、筛选、定位、切换和返回有静态设计；没有可运行交互。
Layout words by section: 总览=数字/状态条；库存=容量/货位列表；订单=队列；详情=属性/关联任务；追溯=时间线；场景=视图控制。
Scores: design 7.5 · usability 7.0 · creativity 7.0 · content 8.0 → overall 7.3
Caps applied: 创意按已知工作台模式的克制执行计 7 分；静态桌面可用性评分不等于运行验证。
Top three problems (most visible first), each with the screenshot it shows in and the fix:
1. 18-order-detail.png：订单“待拣货”与时间线“拣货中”冲突；改为“设备已接单 / 等待开始拣货”。
2. 11-inventory.png：空货位“可分配 0 托”混淆当前数量与容量；改为“当前 0 托 · 可分配 1 托位”。
3. 18-order-detail.png：返回“执行中筛选”与来源列表“全部状态”不一致；改为“返回出库订单 · 保留原筛选”。

以上三项均已改稿并重新导出。

## ROUND 2

Seen in one second: 七个导航有业务名称，列表的下一步是定位或查看详情。
Idea (one sentence): 从总量进入具体对象，查看后能返回原上下文。
Live thing: 动作及状态仍是静态设计。
Layout words by section: 七个侧栏复用一致边距，物料详情与追溯采用属性和时间线结构。
Scores: design 7.5 · usability 7.5 · creativity 7.0 · content 8.0 → overall 7.5
Caps applied: 与 ROUND 1 相同。
Top three problems (most visible first), each with the screenshot it shows in and the fix:
1. 15-material-trace.png：缺少回到所查物料的明确路径；增加“← 返回物料详情 · SKU2038”。
2. 03-poi-group.png、10-group-warning.png：右栏显示总览，但导航选中设备；统一为总览选中。
3. 05-device-history.png：泛称“追溯查询”不明确模式；改为“设备轨迹查询”，提供“切换至物料追溯 →”。

## ROUND 3

Seen in one second: 总览可读到库容和今日规模，其他六项导航各有对应工作内容。
Idea (one sentence): 从仓库态势进入物料、订单、设备与事件的工作界面。
Live thing: 已表达查询、定位、筛选、确认与返回路径，运行行为留待实现验证。
Layout words by section: 总览=汇总；库存=容量/货位；订单=作业队列；设备=状态/列表；告警=分级队列；追溯=时间线；场景=视图控制。
Scores: design 7.5 · usability 8.0 · creativity 7.0 · content 8.0 → overall 7.7
Caps applied: 仅桌面静态稿评分；不推广到移动端、真实用户表现或实际运行。
Top three problems (most visible first), each with the screenshot it shows in and the fix:
1. 本轮范围内无新增静态稿阻断项；物料返回链接已在最终导出确认。
2. 两张聚合页导航已与右栏对齐，独立只读评审复核确认。
3. 不继续扩大风格修改范围；真实鼠标操作、尺寸适配与动效需后续实现时验证。

## 数据与状态核对

- 库容：2400 = 1728 + 96 + 576，占用率 72.0%；A/B 区与总量一致。
- 货架 A-03：48 = 占用 36 + 可用 8 + 空位锁定 4。
- 今日订单：284 = 入库 128 + 出库 156；入库 96+22+8+2，出库 118+24+10+4，合计完成 214、执行 46、等待 18、异常 6。
- SKU2038：480 = 24 箱 × 20 件 = 分配 120 + 可用 360；批次、托盘、货位和关联订单一致。
- 作业设备：106 = 52+16+6+32 = 62+36+5+2+1。
- 设施：56 = 18 充电 + 36 空闲 + 2 离线，不计入作业设备。
- 告警：7 = 5 预警 + 2 故障 = 待确认 4 + 已确认 3；确认不等于恢复，离线设备与订单异常分别统计。
- 零值显示 0，未知/加载值显示 —；局部失败保留并注明旧数据；空锁定货位不提供虚假的物料详情。

演示 JSON 的上述关系已执行断言并全部成立。页面列表为分页示例，不以可见几行冒充全部数据。

## 视觉与验证边界

全尺寸 PNG、侧栏汇总和场景截图已检查。23 张画板无未结束 placeholder；绝对布局边界检查未发现越界；34 个可复用组件保持一致。字号为 12/14/16/20/24/32。蓝色用于交互/选中与容量数据，绿/橙/红用于状态并配文字；数值附单位。

两个独立只读评审分别核对业务与数据、画面与布局，最终修正已复核。未开展真实用户测试、响应式验证、设备控制或浏览器业务测试；未报告 inspect/lint 或交互运行 PASS。
