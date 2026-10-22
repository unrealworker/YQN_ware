# 办公翼转角玻璃立面

当前关卡 `/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory` 已新增独立对象 `GHS_OfficeGlassFacade`，位于 `GHS/Architecture/OfficeFacade`。按用户提供的转角参考图制作深蓝玻璃、浅灰细窗框、白色窗头板和连续转角柱。

西侧短墙采用 3 组窗，正面采用 5 组窗；每组 4 列 × 3 行，共 96 块玻璃。新网格共 2,916 个三角面、5 个材质槽，Blender 中保留 243 个命名部件供后续调整。

## 定位和材质

| 位置 | 仓库局部坐标，米 | 外法向 |
| --- | --- | --- |
| 西侧 | u=0，v=118.872..137.16 | −X |
| 正面 | v=137.16，u=0..45.8724 | +Y |

沿用现有 CAD 墙体：玻璃背面外偏 0.08 m，正面外偏 0.10 m，窗框最外 0.18 m，均在 0.25 m 屋檐内。审计旧墙最大局部外凸 0.053033 m，仍有约 0.027 m 净距。与最近月台门相距约 19.65 m，没有覆盖门洞。

玻璃为不透明的建筑展示饰面，使用深蓝底色、低粗糙度和 Fresnel 掠射蓝色变化；未切穿原有 CAD 实墙，不提供透过玻璃观察室内的效果。五种材质分别为 Glass、Frame、Panel、Pier、Sill，使用 `/Game/GHSZcoolSmartFactory/OfficeFacade` 私有资源。

## 源文件与应用

- `OfficeGlassFacade.blend`：可编辑部件，以及明确标记为不导出的预览环境。
- `SM_GHS_OfficeGlassFacade.fbx`：单个网格，原点导入，单位缩放。
- `facade_manifest.json`：坐标、材质、部件统计、门洞净距和原始资料哈希。
- `office_facade_preview.png`：Blender 建模预览；项目最终效果以 `Review` 中实际 UE 运行截图为准。
- `fbx_roundtrip_verification.json`：FBX 回读验证结果。

生成器：`Scripts/ghs/build_office_glass_facade.py`。UE 应用：`Scripts/ghs/apply_office_facade.py`。只读验证：`Scripts/ghs/validate_office_facade.py`。现有运行验收可添加 `-OfficeFacadeCapture` 获取转角、近景、隐藏屋顶和园区总览截图。

应用脚本要求先保存现有场景，读取 `Saved/OfficeFacade/Before/scene_state.json` 基线，逐一核对原有 360 个对象的变换、组件、材质绑定、标签和实例数据。添加后关卡为 361 个对象。立面无碰撞、无 Tick、无业务身份，不参与标签与设备统计；独立屋顶显隐不会改变立面。

最终验收见 [Review/acceptance.json](Review/acceptance.json)，实景见 [Review/OfficeFacade_Corner.png](Review/OfficeFacade_Corner.png)。此处的验收是编辑器资源和独立 game 运行检查；没有重新打包 EXE，也不代表像素流性能测试。
