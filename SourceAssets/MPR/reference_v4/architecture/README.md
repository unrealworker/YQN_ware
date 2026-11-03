# MPR V4 主仓外壳与屋面

主仓保留原 CAD 的 16 段外墙轮廓、74 个门洞和内外地坪/屋面接口，不生成或修改内部地板、柱、隔墙和设备。新图 `../references/all-elements-outline-20261103.png` 决定屋顶光伏与设备布局；旧彩色效果图仅作为材质和细节风格参考，不再用旧透视相机确定光伏落点。

`plan_solar_v5.json` 保存人工核对的 16 个正交光伏区域、主要白通道及 U/C/E 形大开口。线稿网格断线、单格白洞和像素锯齿不作为真实设备洞口；边界是示意图判读，仍含约 1.5 像素不确定性。模块需完整落在允许区域内，采用真实尺寸模块采样，图上格子数不等于真实模块数量。

当前清单包含 5,147 个视觉模块，合并为 533 条连续板带；5 个 SolarBank 分区各保留 LOD1。银框、支脚和电池片贴图用于近景，远处 LOD 简化细小构件。底座为无顶盖壳体，避免与电池片争夺深度；UE SolarBank 关闭 Nanite，按 `lod_files` 绑定显式 LOD，不能把 LOD1 另外放入场景。

屋顶设备来源为 30 个独立线稿符号，当前实际放置 29 个共享采光箱；位置对应 `source_pixel`，不按列表索引推断。投影对应和未放置源符号见 `../validation/plan_alignment.json`。屋面仍使用 6.1 m 网格、0.15 m 视觉板缝和蓝色薄檐；板缝宽度、设备高度与细节是风格化估计，不作为工程测量。

`mpr_reference_shell.blend` 包含可编辑分区、隐藏模块库、共享实例和打包贴图。`reference_shell_manifest.json` 当前为 62 个 LOD0 网格、5 个 LOD1 网格、714 个实例；LOD0 为 108,180 三角面，全部交换网格为 114,576 三角面。最终材质顺序、PBR 参数、纹理路径、边界和 LOD 对应以清单为准。

`fbx_validation.json` 由 `Tools/MPRWarehouse/validate_mpr_reference_shell_v4.py` 回读实际 FBX，检查哈希、边界、三角面、材质、UV、非退化面、CAD 轮廓及门洞。新图光伏边界检查见 `../validation/plan_solar_polygon_validation.json`；实际板带落点与完整 UE 视图分别见 `../validation/plan_alignment.json` 和 `../validation/runtime_views/03-roof.png`。这些证据必须与当前源清单及本轮归档哈希一致，旧顶盖修复报告不能代替当前输出验证。

生成入口为 `Tools/MPRWarehouse/build_mpr_reference_shell_v4.py`，几何/材质工具为 `mpr_reference_shell_v4_lib.py`。新平面坐标经过 `mpr_plan_layout.py` 独立注册，模型保持 CAD 米制。旧相机预览仅作风格检查；源几何或相机校验通过不代表 UE 远景抗锯齿、阴影、性能或整场外观已达到完美 1:1。
