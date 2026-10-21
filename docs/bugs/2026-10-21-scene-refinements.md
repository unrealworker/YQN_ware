# 仓库颜色、70%库存和场景控制修正

范围：`/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`。

后续变更：地堆已按用户最新要求恢复满载，货架继续约70%；卷帘门增加1–87编号，搜索框同步动画。当前状态和验收见 `2026-10-21-dock-numbers-search-motion.md`。下方保留本轮原始记录。

## 已实现

- 地面 `GHS | DIGITAL TWIN`、`RACK STORAGE`、`PALLET STORAGE` 使用实际货架 `M_Zcool_Cobalt.SurfaceTint` 的深蓝色。线性 RGB 为 `(0.018, 0.075, 0.51)`；TextRender 的线性顶点色量化为 `(5, 19, 130)`。
- 实际挂载的 36 个 Zcool 特效材质实例（40 个 Decal 组件）使用相同 Tint；父材质、Time 动画、Speed、Phase、OpacityScale、EmissionScale 保持。
- 右侧缩放/复位控件的绘制和点击区域共用面板每帧动画位置，保持 20px 间距。小于 900px 宽的底部面板布局中，控件保持在场景区右下方，避免被横向移动的面板遮挡。
- 货架 1,629 实例、完整结构均保留；25,056 个托位保留 17,539、留空 7,517，占用率 69.9992%。地堆 7,530 个位置保留 5,271、留空 2,259，占用率 70%。
- 新建 10 个私有货架网格与 3 个地堆网格副本，HISM 组数不增加。货架空位的托盘、纸箱、标签从几何中移除；空槽从物料命中元数据排除。地堆保留实例按原顺序重建，并同步其 CAD ID。
- 中键点击在场景区域复用 overview，取消拖动、平滑复位并清除设备/物料/POI 选中态；面板区域不会误触场景复位。
- 总览及库存页的演示库存同步为 70%；48 格演示矩阵为 34 占用 / 10 可用 / 4 锁定。仍明确标注为业务演示，未将示例业务容量等同于场景几何托位数。

## 验证

- UE 5.4.4 / MSVC 14.38 编译成功：`Saved/SceneRefinements/build.log`。
- 全部 GHS UE 自动化：83 成功，0 失败，0 警告：`Saved/SceneRefinements/Automation/index.json`。
- 网页测试：51/51：`Saved/SceneRefinements/web-tests.log`。
- 实际离屏 UE：1920×1080 和 600×900，共 19 项控件/交互检查；逐帧验证收放、反转、运动中热区缩放与复位清选中：`Saved/SceneRefinements/controls_runtime.json`。
- 真实 Windows 鼠标中键点击：AGV-34 选中 → overview，Selection 为空、ObjectPivot=false：`Saved/SceneRefinements/middle_acceptance.json`，前后状态在 `middle_before.json` / `middle_after.json`。
- 地图保存后重新载入；248 个 Actor 不变，所有新实例位置和 CAD 元数据一致，原 NormalWarehouse 地图和共享模型/材质哈希未改变：`Saved/SceneRefinements/apply_report.json`。
- 近景截图：`Saved/SceneRefinements/racks.png`、`floor.png`、`agv34.png`。可见真实空位、完整框架和深蓝特效。

仅货架 LOD0 的实例加权三角数减少约 26.82%；这不是本次帧率提升测量。本次未重做性能基准或重新打包，交付范围为当前项目的源代码、素材、场景和编辑器运行状态。

## 可复现与恢复

- 离线资源生成：`Scripts/ghs/build_zcool_occupancy.py`；输出 `SourceAssets/GHS/ZcoolOccupancy/zcool_occupancy.json` 和 FBX。
- UE 应用/重载验证：`Scripts/ghs/apply_scene_refinements.py`，仅允许目标 Zcool 地图。
- 首次执行前备份：`Saved/SceneRefinements/Backup`，包含目标地图、私有素材以及两份原元数据。
- UI 的深蓝特效改色同时覆盖原本共享这些实例的堆高车；旧 NormalWarehouse 特效不变。
