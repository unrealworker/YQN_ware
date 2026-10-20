# GHS 仓储数字孪生 · 业务页面、HUD 与 POI 设计

当前交付为 Pencil 可编辑静态设计：**23 张 1920 × 1080 画板、34 个可复用组件**。本轮在完整业务页面上增加设备模型图片、指标卡、容量环图、订单趋势、状态条形图、货位矩阵和视角缩略图。未开发业务，也未制作可运行的点击原型。

## 打开设计

- [Pencil 主文件](C:/Users/28109/.pencil/documents/ddf468b1-64d1-4a74-8f7f-a5f24bff996f/untitled.pen)
- [七个侧栏页面与设备详情](exports/visual-v4/sidebar-contents.png)
- [场景与设备图片](exports/visual-v4/scene-and-equipment.png)
- [图片与图表重点预览](exports/visual-v4/visual-highlights.png)
- [本轮 taste-skill 视觉评审](taste-visual-review.md)
- [业务设计说明](business-design-brief.md) · [演示数据](business-demo-data.json)

主文件保存在 Pencil 应用管理目录。本目录保存参考、截图、说明与 PNG 导出；最新版为 exports/visual-v4/，旧稿 business-v3、taste-v2 和 before-taste 保留。早期评审记录见 taste-review.md、taste-revision.md。

## 七个侧栏的内容

| 入口 | 先回答的问题 | 内容与下一步 |
| --- | --- | --- |
| 总览 | 仓库是否正常、今天任务多少？ | 库容、可用托位、今日出入库、设备状态、关注事件；进入对应业务 |
| 库存 | 哪些货位有空间、物料在哪里？ | 全仓/区域容量、货架货位、SKU/批次搜索、占用/可用/锁定筛选；查看物料 |
| 订单 | 哪些出入库订单需要处理？ | 入库/出库切换、状态统计、搜索筛选、订单列表及详情；定位执行设备 |
| 设备 | 哪台设备异常、在做什么？ | 106 台作业设备及五类状态、56 个充电设施独立切换；定位、任务及详情 |
| 告警 | 哪些故障未恢复、有人确认了吗？ | 分级队列、确认/恢复状态、告警详情、关联设施；确认及查看历史 |
| 追溯 | 物料经过哪里、设备怎样运行？ | 物料批次流转与设备轨迹查询；时间、地点、作业及订单串联 |
| 场景 | 怎样看到当前关心的对象？ | 视角预设、图层、路线、POI、告警、标签密度；应用和恢复默认 |

## 核心路径

- 库存 → 货架 A-03 → 货位 A-03-12 → 物料 SKU2038 → 关联订单 / 物料追溯。
- 订单 → OUT-20261020-121 → 查看数量、源货位、目标月台和任务 → 定位 FORK-01。
- 告警 → AGV-12 低电量 → 查看阈值与确认/恢复状态 → 关联充电位 / 历史轨迹。
- 返回保留筛选、选中对象和日期范围，避免查看详情后丢失上下文。

物料详情包括名称、SKU、规格、批次、托盘、货位、入库时间、480 件库存、120 件已分配、360 件可用及关联订单。空货位、锁定、无结果、零订单、加载、局部失败和确认未恢复均有状态设计。

## 全部画板

| 编号 | 内容 | 文件 |
| --- | --- | --- |
| 00 | POI 与 HUD 设计系统 | [预览](exports/visual-v4/00-poi-system.png) |
| 01 | 仓库运营总览 | [预览](exports/visual-v4/01-business-overview.png) |
| 02 | 设备详情 | [预览](exports/visual-v4/02-device-detail.png) |
| 03 | 聚合点位展开 | [预览](exports/visual-v4/03-poi-group.png) |
| 04 | 告警详情 | [预览](exports/visual-v4/04-alert-detail.png) |
| 05 | 设备轨迹查询 | [预览](exports/visual-v4/05-device-history.png) |
| 06 | 库位悬停预览 | [预览](exports/visual-v4/06-bin-hover.png) |
| 07 | 车辆与设施 HUD | [预览](exports/visual-v4/07-hud-library.png) |
| 08 | 系统状态 | [预览](exports/visual-v4/08-system-states.png) |
| 09 | 交互规范 | [预览](exports/visual-v4/09-interaction-spec.png) |
| 10 | 聚合预警筛选 | [预览](exports/visual-v4/10-group-warning.png) |
| 11 | 库存容量与库位 | [预览](exports/visual-v4/11-inventory.png) |
| 12 | 出库订单 | [预览](exports/visual-v4/12-outbound-orders.png) |
| 13 | 设备状态 | [预览](exports/visual-v4/13-devices.png) |
| 14 | 告警中心 | [预览](exports/visual-v4/14-alerts.png) |
| 15 | 物料追溯 | [预览](exports/visual-v4/15-material-trace.png) |
| 16 | 场景设置 | [预览](exports/visual-v4/16-scene-settings.png) |
| 17 | 货架物料详情 | [预览](exports/visual-v4/17-material-detail.png) |
| 18 | 出库订单详情 | [预览](exports/visual-v4/18-order-detail.png) |
| 19 | 入库订单 | [预览](exports/visual-v4/19-inbound-orders.png) |
| 20 | 充电设施 | [预览](exports/visual-v4/20-charging-facilities.png) |
| 21 | 导航与业务流程 | [预览](exports/visual-v4/21-navigation-map.png) |
| 22 | 业务边界状态 | [预览](exports/visual-v4/22-business-states.png) |

## 视觉和数据

延续 Saas.gif 与站酷参考：灰白仓库、白色业务信息层、蓝色交互强调、窄深色顶栏。空间和点位承担定位；右栏承载判断和行动。侧栏增加中文名称。

演示快照为 2026-10-20 14:20:08。2400 托位 = 占用 1728 + 空位锁定 96 + 可用 576，占用率 72.0%。今日 284 单 = 入库 128 + 出库 156。设备与设施分开；7 项设备告警不与 6 单订单异常混算。

设计沿用 GHS_CAD_NormalWarehouse 设备分类与 HUD 语义；库存、订单、追溯等扩展不表示原项目已接入。数值为演示数据，POI 为设计示意，未绑定世界坐标。

## 验证

23 张画板无未完成占位标志，绝对布局边界未发现越界；34 个可复用组件，字号统一为 12/14/16/20/24/32。库存、分区、货架、订单、物料分配、设备、设施与告警的关系已通过断言核对。全尺寸 PNG 已检查，两个独立只读评审核对了业务与视觉，修正已复核。

结论仅针对桌面静态设计与演示数据，不代表点击行为、设备控制、接口、响应式或 Unreal 功能经过运行验证。本轮未改动 Unreal 场景或业务代码。

交付日期：2026-10-20。


