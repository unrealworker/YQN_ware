# 主厂房四面玻璃立面

当前关卡 `/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory` 复用独立对象 `GHS_OfficeGlassFacade`，位于 `GHS/Architecture/OfficeFacade`。本版按用户四张参考图扩展厂房北、西、东、南面窗组，并将蓝色玻璃略微调浅；浅灰细窗框、白色窗头板和转角柱延续既有风格。

原西南办公翼的侧面 3 跨、正面 5 跨及 243 个源部件几何保留。本版新增 15 组、35 跨，合计 **43 跨、400 块玻璃**；同一网格共 **13,380 个三角面、5 个材质槽**，Blender 中有 **1,115 个命名部件**。复用原 Actor，关卡仍为 361 个对象。

## 定位和材质

| 位置 | 窗型 | 玻璃高度 Z，米 |
| --- | --- | --- |
| 原西南办公翼两面 | 原有落地窗，8 跨 | 0.24..6.54 |
| Glen Helen 北墙、西墙 | 高位横窗，下方保留实墙 | 6.50..8.20 |
| 东北办公角两面 | 下段近地、上段横窗，中间白墙带 | 下段 0.24..3.30；上段 5.70..7.90 |
| 东侧月台窗组 | 高位横窗，下方保留原墙 | 7.55..8.95 |
| 南侧三组月台立面 | 高位横窗配全高柱、下接门头的白面板 | 7.55..8.95 |
| 东南斜角及南侧末端 | 高位横窗 | 7.05..8.65 |

沿墙坐标与窗组配置以 [facade_layout.json](facade_layout.json) 为准：墙面依照既有 CAD 外轮廓，窗组长度、跨数和高度由用户照片推定，属于展示复原，不是测绘窗洞。玻璃背面外偏 0.08 m，正面外偏 0.10 m，窗框最外 0.18 m；旧墙局部最大外凸 0.053033 m，玻璃仍有约 0.027 m 净距。

南侧三组按实际月台编号定位：**75–78 号对应 2 跨、51–53 号对应 3 跨、30–33 号对应 2 跨**。宽 0.60 m 的全高柱落在门间墙缝；白色面板从 Z=4.25 m 接至玻璃底 Z=7.55 m，形成与卷帘门相连的完整门头。门洞净高 4.2 m 保持。

这三组共 11 个编号仅沿立面外法线 **+Y 平移 20 cm**，使文字位于新面板前；X、Z、字号、字体、颜色和材质均保留。TextRender 实际字形组件高度约 Z=5.5..6.7 m；先前 Actor 球形包围最高 7.38 m 并非字形顶高。东侧月台仍用上部短柱，不与南侧全高门头混同。

玻璃为不透明的建筑展示饰面，使用略浅的蓝色、低粗糙度和 Fresnel 掠射变化；未切穿原有 CAD 实墙，不提供透过玻璃观察室内的效果。Glass 线性底色为 `(0.027,0.085,0.155)`，掠射色为 `(0.085,0.18,0.275)`。五种材质分别为 Glass、Frame、Panel、Pier、Sill，位于 `/Game/GHSZcoolSmartFactory/OfficeFacade`。用户手工给屋顶 Skylight 槽设置的 `M_GHSFacade_Glass` 绑定保留，因此采光带也沿用这次调浅后的玻璃色。

## 源文件与应用

- `OfficeGlassFacade.blend`：可编辑部件，以及明确标记为不导出的预览环境。
- `SM_GHS_OfficeGlassFacade.fbx`：单个网格，原点导入，单位缩放。
- `facade_layout.json`：四面新增窗组的位置、分型和月台编号保护高度。
- `facade_manifest.json`：坐标、材质、部件统计、门洞净距和原始资料哈希。
- `office_facade_preview.png`：Blender 建模预览；项目最终效果以 `Review` 中实际 UE 运行截图为准。
- `fbx_roundtrip_verification.json`：FBX 回读验证结果。

生成器：`Scripts/ghs/build_office_glass_facade.py`。UE 应用：`Scripts/ghs/apply_office_facade.py`。只读验证：`Scripts/ghs/validate_office_facade.py`。现有运行验收可添加 `-OfficeFacadeCapture` 获取转角、近景、隐藏屋顶和园区总览截图。

本轮基线和验证输出位于 `Saved/FacadeExpansion`，不沿用首次办公翼的 `Saved/OfficeFacade` 成功记录。应用与验证逐一核对当前 361 个对象的变换、组件、材质绑定、标签和实例数据；只允许上述 11 个编号沿 Y 外移 20 cm，并保留原办公翼几何及用户屋顶采光带绑定。立面无碰撞、无 Tick、无业务身份，不参与标签与设备统计；独立屋顶显隐不会改变立面。

当前验收状态及地图、源文件、截图哈希见 [Review/acceptance.json](Review/acceptance.json)，原始输出位于 `Saved/FacadeExpansion`。归档范围为四面扩窗、南侧三组门头近景、开顶及总览的 **13 张实景**；本版验收以新文件记录为准，不沿用历史成功结论。验收针对编辑器资源和独立 game 运行，不代表重新打包 EXE 或像素流性能测试。
