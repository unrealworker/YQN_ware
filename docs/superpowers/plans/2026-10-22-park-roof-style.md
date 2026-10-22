# 主厂房屋顶与柔和园区风格实施计划

**Goal:** 按用户参考图完成浅色独立屋顶、柔和树冠与场景光影，同时保留可见内部的后续交互结构。

**Architecture:** 沿当前厂房精确轮廓建立独立静态屋顶，全部细部合并为一个多材质网格和一个 Actor。只更新三种树冠网格法线、私有树材质及有限光影设置，不改 CAD 道路、设备布局和用户地面材质。

**Tech Stack:** Blender 5.2、UE 5.4、现有 Python 生成与编辑器导入流程。

**Spec:** 用户 2026-10-22 所附 `codex-clipboard-0df2ba29-2688-4912-a76f-f19056c0ec63.png`；交互屋顶属于后续功能，本次建立整体显隐结构并验证隐藏后内部仍完整。

## 约束与验收重点

- 精确厂房轮廓来自 `SourceAssets/GHS/RefinementV2/Envelope/envelope_geometry.json`，墙顶 9.6 m，不改现有墙体或货架。
- 屋顶为浅坡金属屋面，5 条纵向蓝色采光带、细立边缝、蓝色包边和少量通风帽，采用不透明材质。
- 屋顶不得带业务 ID、POI、碰撞或 Tick；所有部件整体显隐。
- 保留用户 Ground→Landscape、Blue→Cobalt 材质覆盖、Ground 原有位移及其他未保存材质。
- 保持既有树位、数量、模型轮廓和面数；仅平滑树冠法线、调整三档绿色。
- 不启用新的重型渲染特性；白屋面不过曝、接触阴影不过黑，内部焦点视角仍可验收。

## 实施

- [x] 保存编辑器当前 Actor、材质与光影快照，建立本轮独立恢复基线。
- [x] `Scripts/ghs/build_main_warehouse_roof.py` 生成 `SourceAssets/GHS/MainRoof` 的可编辑 Blender、FBX、材质和几何报告；核对边界覆盖、9.6 m 底标高、采光带数量和预算。
- [x] 更新 `park_vegetation.py` 三档绿色和 `build_park_geometry.py` 树冠平滑法线；完整重建后核对全部几何位置及数量未变。
- [x] `apply_park_roof_style.py` 在现有关卡中导入独立屋顶、更新三种树冠及材质，并保存；非目标资产不得改写。
- [x] UE 实拍检查总览、屋顶近景、圆润树冠与隐藏屋顶后的内部；保存后独立重载并验证原 Actor 保留、屋顶材质和显隐结构、地面覆盖及业务注册。
- [x] 更新当前评审图片与说明，中文提交本地 `master`。
