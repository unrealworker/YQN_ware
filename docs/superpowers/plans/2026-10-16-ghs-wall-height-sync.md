# 两套仓库的建筑墙高同步修正

用户指出此前整体拔高遗漏墙体，并明确要求同时修改深蓝与浅灰关卡。

根因：`prepare_visual_layout.py` 原提升列表仅包含货架、货堆、柱和柱轮廓。两张关卡的实际建筑墙均为 2.8 m，柱为 5.6 m，主货架为 4.8 m。

修正：两张关卡的墙面与封顶实例 Z 比例从 1 改为 2；顶部轮廓 Z 位移增加 2.8 m，仍保持封顶上方 0.5 mm。CAD 平面尺寸、12 mm 内收轮廓宽度、门洞、地面门扇线和设备支撑短隔板保持不变。5.6 m 是与已有柱高协调的展示估算高度，非实测建筑标高。

共享高度定义：`SourceAssets/GHS/wall_height_profile.json`。两场景 registry 与 presentation visual_layout 同步记录此定义，后续生成高度布局也应用该定义。

- [x] 从两张已保存 UE 关卡读取实际高度。
- [x] 备份两地图、三 registry 和所有 Content 哈希。
- [x] 同步应用两场景六个墙体实例变换并保存。
- [x] 独立 UE 重新加载检查世界三角、封顶闭合、轮廓贴合、门洞与 CAD 并集面积；非墙 Actor 状态与材质灯光逐项比较。
- [x] 两种风格同视角截图和两套完整回归均通过。三次独立 UE 验收退出码均为 0；659 个非地图 Content 文件未改动。两套截图位于 `Saved/GHS_WallHeight_*_UE_WallDetail.png`，并排预览 `Saved/GHS_WallHeight_Synchronized.jpg`。

证据：`Saved/GHS_WallHeightBefore.json`、`Saved/GHS_WallHeightSync.json`、`Saved/GHS_WallHeightVerification.json`。本次修改保留历史 hash 基线，通过精确的 before/after SHA 和原文件备份记录用户授权的五文件变更。

后台保存浅灰场景时，当前交互编辑器占用其文件。完成前确认现场无未保存修改，随后在该编辑器应用同样的三个实例变换并保存。比较场景属性时去除 UE struct repr 的进程地址，忽略只在交互编辑器存在的相机编辑图标；实际相机位置和参数仍严格比较。
