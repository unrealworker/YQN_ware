# 仓库视觉增强

本目录的四层货架和5.6 m柱高属于早期视觉增强历史。CAD货架修订以 `../RackSpecs/README.md` 为准：两场景同步为1639个A/B/D1货架（含跨通道），C/D2只在资产库，87个W_DOCK实体为装卸门。货架柱高按图为9.144/9.154 m；建筑9.6 m和门高4.2 m属于展示假设。`visual_layout.json` 随新修订保存当前映射，其余早期源模型、材质方案和报告保留供追溯。

保持 CAD 的库位、通道、柱位及已完成避让，调整垂直层次和蓝色材质。高度是展示设定，不代表现场测绘结果。

- 主货架 4.8 m，四层；装卸区货架保留原高度。
- 7408 个地堆按 166 个连续区块分为约 1.38 / 1.98 / 2.58 m，保留正常托盘厚度和箱体层高。
- 170 根柱子提高到 5.6 m，2040 条边线随柱体重新闭合。
- 新网格在 Blender 中生成，保持原平面范围内；三种地堆共享材质。18 个 HISM 组、14116 个实例；四种新增网格均有四级 LOD。
- 深蓝默认光照材质：较亮顶面、深色侧面、暗内腔及细青色接缝。AGV、墙面与动态扫描特效继续使用原资产。
- 场景仅一盏方向光及一盏指定 Cubemap 的环境光；方向光提供投影，SkyLight 无阴影、无实时捕获，场景不使用 Lumen 和局部补光灯。

`presentation_storage.blend` 和四个同名 FBX 是可编辑模型；`presentation_storage.json` 记录原点、尺寸和材质槽。`visual_layout.json` 记录最终实例和高度分区，`material_style.json` 控制表面颜色等参数，上一级 `lighting_style.json` 控制照明。

旧建模入口为 `Scripts/ghs/build_presentation_storage.py`（后台 Blender）。完整旧重建链 `build_ue_scene.py` → `rebuild_presentation_refinement.py` 仅适用于修订前版本。它们以及 `prepare_visual_layout.py`、`apply_presentation_layout.py` 已加保护，存在CAD货架修订时在写入前停止，防止恢复通用四层货架。当前修改使用 RackSpecs 中的规格、平面映射、专用模型和受备份保护的修订流程。

检查入口仍为 `Scripts/ghs/verify_ue_scene.py`。它与 `verify_presentation.py` 均在成功货架修订存在时转入 `verify_cad_rack_revision.run()`，验证两套保存关卡，并写入 `Saved/GHS_CADRackVerification.json`。旧 `Saved/GHS_PresentationVerification.json` 保留，不重写。

固定相机对照图：`Saved/GHS_PresentationBefore_UE_*.png`；最终从磁盘重新加载的带投影版本：`Saved/GHS_PresentationReload_UE_*.png`，汇总为 `Saved/GHS_PresentationComparison.jpg`。

材质更新会循环清空旧表达式再重建，避免 UE 5.4 单次 DeleteAllMaterialExpressions 遗留同名旧参数。保存前核对参数默认值，重新启动后再次核对保存的材质连线和参数。

性能报告为编辑器视口采样，不能直接等同于打包程序或所有设备的帧率。固定视角 GPU 平均约 8.8 ms，8 秒横移 25 m 的原始样本约 9.0 ms；移动采样中有一次编辑器停顿及少量无效 GPU 查询，不能据此声称全程无卡顿。性能采样早于最终重复参数清理，模型、灯光和实际连接的材质图相同。
