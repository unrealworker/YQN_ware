# GHS CAD 货架修订维护说明

两套关卡共用本目录的 CAD 几何与实例映射：`/Game/Maps/GHS_CAD_DigitalTwin` 和 `/Game/Maps/GHS_CAD_NormalWarehouse`。深蓝与浅灰配色通过独立组件材质保持；本修订不调整 AGV、绿色动态 Decal、充电设备或照明。

## 图纸依据与实际放置

`cad_elevation_specs.json` 从原始 DXF 的五类立面提取尺寸，并保留源 handle、尺寸实体测量值及显示文字。A、B、C、D2 的图示层数包含地面托盘层，不能再多加一道底梁。

| 主体现状图内的货架 | 实例数 | 垂直结构 |
|---|---:|---|
| A | 1214 | 地面 + 3 道上层，柱高 9.154 m |
| A 跨通道 | 47 | 仅上部 2 层，梁下净空 4.4704 m |
| B | 265 | 地面 + 11 道上层，柱高 9.154 m |
| B 跨通道 | 11 | 仅上部 6 层，梁下净空 4.484 m |
| D1 | 102 | 仅上部 2 层，梁下净空 4.4704 m |
| 合计 | 1639 | 保留原 1617 个显示段身份，补全 22 个图纸跨通道货架 |

C、D2 只有详图规格，未找到可确认的当前主体平面放置位置，因此保留在 Blender/UE 资产库中，不随意放入仓库。`cad_plan_mapping.json` 记录实际分类、颜色/属性/图层依据、避柱分段和新增跨通道实体。

原来被叫作“87 个 Dock 货架”的 `W_DOCK` 实体实际是带 `DOCK_NO.` 属性的装卸门。其实体平面位置、约 3.04165 m 宽度及导轨厚度取自 CAD；**4.2 m 门高是展示估算**，不是图纸立面尺寸。D1 货架来自真正的货架实体，与这 87 扇门分别统计。

货架使用真实米制几何，实例缩放为 1。原有共享端框避让和柱旁局部分段保留，截短跨距使用专门网格，立柱、货物和托盘没有整体压缩。C 为 60 英寸深，其他类型为 42 英寸深；40×48 英寸托盘在 42 英寸架体两侧各悬挑 3 英寸，属于图纸侧视可见尺寸。

建筑墙体、170 根柱子及轮廓同步采用 **9.6 m 展示包络**，用于容纳图示 9.144/9.154 m 货架；这不是实测建筑高度。`CLEAR 30'` 属于货架详图净高信息，不能据此宣称已测得建筑屋顶高度。墙体平面厚度与门洞保持原 CAD 数据。

## 维护与验收

当前修订流程为：CAD 规格/平面映射 → `build_cad_rack_models.py` → `prepare_cad_rack_registry.py` → `audit_cad_rack_solids.py --rack-z 0 --column-height 9.6` → `import_cad_rack_models.py` → `apply_cad_rack_revision.py` → `verify_cad_rack_revision.py`。必须先建立 `Saved/GHS_CADRackCheckpoint.json` 所引用的地图、注册表和原资产备份。应用脚本是一次修订操作，已有修订报告时会停止；后续修改应建立新的受控修订，不能删除报告后直接重跑。

`Saved/GHS_CADRackRevision.json` 的 `success` 记录保存结果；`Saved/GHS_CADRackVerification.json` 的 `success` 记录新 UE 进程验收。验收目标为两场景各 **43 组 HISM、14138 个实例**，蓝色/浅灰场景分别 252/254 个 Actor。未生成成功报告时，不以本 README 代替运行验收结论。

`verify_ue_scene.py`、`verify_normal_scene.py`、`verify_presentation.py` 在发现成功修订后转入同一个双场景验收入口，不覆盖各自的历史报告。修订未完成或注册表存在修订而报告缺失时会明确停止。

旧 `build_ue_scene.py`、`build_normal_scene.py`、`rebuild_presentation_refinement.py`、`prepare_visual_layout.py` 和 `apply_presentation_layout.py` 已加保护：检测到修订即停止，防止重建回通用四层货架。旧 `Saved/GHS_*Verification.json` 和旧构建记录作为历史保留，不能用旧 18 组/14116 实例、4.8 m 货架或 5.6 m 建筑值判断本修订。

五张 `CAD_Rack_A/B/C/D1/D2.png` 为图纸立面重绘证据；`Models/cad_rack_models.json` 记录 33 个货架网格、材质角色、实际边界和 FBX SHA；`Doors/cad_dock_door.json` 单独记录装卸门。源 DXF 不修改。

最终两场景保存与重新加载验收均已通过，UE 验收进程为 0 错误、0 警告。`Saved/GHS_CADRackVisualReview.json` 汇总两场景 12 张已检查截图及最新相机、图片 SHA、地图 SHA；其中 D1 视图已从暂存通道重新拍摄，使用各自 `DockD1_2UpperLevels_CaptureReport.json` 的最新记录。`Saved/GHS_CADRack_Comparison.png` 为全景与 B 型货架并列预览，所有截图均未改写地图。
