# Glen 道路两端端帽修正

仅处理 `glen:start` 与 `glen:end`，对应原位 `(u,v)`：

- 西端：`(-197.0, -56.6361106703)`；UE 世界厘米约 `(-43633.385, -11687.6301)`。
- 东端：`(695.3410811045, -20.2369343701)`；UE 世界厘米约 `(45600.7231, -8047.7124)`。

以原 `SourceAssets/GHS/Park/GHS_Park_Source.blend` 的 `SM_GHSPark_Curbs` 为输入，裁去两个 19 米车道接缝内的 10cm 人行道与 19cm 路沿端帽。55 个原面受局部裁剪，109,877 个原面顶点坐标逐面保留；两个高度层共移除约 76.7601 平方米。专用输出为 `SM_GHSRoadEndcaps_Curbs.fbx`，161,319 个三角形。没有新增遮挡板。

`road_endcaps.json` 记录裁剪开口、逐面数量、材质槽、FBX 校验值以及原 Park/ContextTransition FBX 和车流路径的保护校验值。原资源不覆盖。`park_site.py` 同时应用相同开口规则，后续完整生成时不会再封住这两端。

## 构建与验证

```powershell
& 'D:/WinAPP/Blender/blender.exe' --background --python-exit-code 1 --python 'D:/UEPro/Test/Scripts/ghs/build_road_endcaps.py'
& 'D:/WinAPP/Blender/blender.exe' --background --python-exit-code 1 --python 'D:/UEPro/Test/Scripts/ghs/test_road_endcaps.py'
& 'D:/WinAPP/Blender/blender.exe' --background --python-exit-code 1 --python 'D:/UEPro/Test/Scripts/ghs/preview_road_endcaps.py'
```

验证涵盖两个车道内无横挡、两侧路沿与人行道保留、原路及延长路面连续、完整构建的开口规则与专用网格一致。`-- --baseline` 检查旧源几何，预期失败；失败证据保存在 `Saved/road-endcaps-red.log`。现有道路/曲线/围栏/交通 Python 测试 35 项也通过。

`Review` 是 Blender 源几何俯视对比图，不能替代 UE 实景验收。

## UE 集成（由父任务统一执行）

停止 PIE 后通过现有 dispatcher 运行 `Scripts/ghs/apply_road_endcaps.py`，或在编辑器关闭时使用 Python commandlet。脚本只导入一个新网格到 `/Game/GHSZcoolSmartFactory/RoadEndcaps/Meshes`，把现有 `GHSPark_Curbs` Actor 换为该网格；原网格静态材质槽、组件材质覆盖、Actor/组件变换与全场其他 Actor 均严格比较保持一致。保存地图并输出 `Saved/SceneControls/RoadEndcaps/apply.json`。

随后运行只读脚本 `Scripts/ghs/verify_road_endcaps_scene.py`。它核对已保存的替换网格、园区/环境 Actor、地面材质与变换及保护源文件，输出 `scene-validation.json`。UE 导入、保存后复验以及两端实景截图需由父任务执行并确认，源资产阶段不将其标为已完成。

2026-10-23集成结果：已导入并保存目标场景，保护项检查通过。两端UE实景截图已目视确认横挡移除、侧沿保留：`Saved/SceneControls/Runtime/20261022_190906/06-west-road-mouth.png`、`07-east-road-mouth.png`。完整验收见 `docs/scene-controls-validation-20261023.md`。
