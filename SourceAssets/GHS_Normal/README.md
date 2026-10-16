# GHS 视频风格仓库

新关卡：`/Game/Maps/GHS_CAD_NormalWarehouse`。

依据 `D:/DDDownload/normal_video.mp4` 的 6.44、9.20、25.76、28.56 秒画面，采用浅灰展示环境、银白货架、工业蓝托盘和层板、牛皮纸货箱。参考帧和联系表位于 `Reference/`。视频中的品牌片头及软件界面不属于仓库模型。

关卡与深蓝版共用 GHS CAD 布局、厚墙、柱体、货架、货堆、KUKA AGV 和充电设备，并保留 122 个柱旁避让货位。本轮按 CAD 立面换成 A/B/D1 共1639个货架实例（含跨通道版本），C/D2仅保留在资产库；原87个W_DOCK对象修正为装卸门。货架柱高按图为9.144/9.154 m；两场景建筑墙/柱/轮廓同步采用9.6 m展示包络，装卸门4.2 m高度均为估算。完整依据与维护流程见 `../GHS/RackSpecs/README.md`。没有新增 CAD 未标明的输送线。

材质与特效均独立存放在 `/Game/GHSNormalWarehouse`，通过组件覆盖应用，不修改共享网格默认材质。`material_style.json` 和 `lighting_style.json` 保存本场景的配色及照明参数。AGV 雷达扫描与底部扩散保留 Time 驱动的动态 Decal，沿用原 GHS 绿色 `[0.04, 0.8, 0.30]`。浅色地面上使用 `OpacityScale=1.8`、`EmissionScale=0.12` 增强线条与拖尾，保持受控发光。

照明采用一盏方向光和一个固定环境立方体 SkyLight，无点光源阵列。固定曝光、低 bloom、受控 AO 提供明暗层次；继续使用 HISM 实例化。没有针对性能做未经测量的帧率承诺。

## 重建和验收

- `Scripts/ghs/build_normal_scene.py`：历史初次克隆入口；存在 CAD 货架修订时明确停止，避免覆盖当前几何及材质。
- `Scripts/ghs/verify_normal_scene.py`：存在成功货架修订时调用 `verify_cad_rack_revision.run()`，在新 UE 进程中验收两套关卡；不覆盖旧Normal验收报告。
- `Scripts/ghs/capture_normal_scene.py`：输出四个相机视角的真实 UE 渲染，不保存场景或资产。
- `Scripts/ghs/open_normal_scene.py`：在当前 UE 编辑器打开新场景；如果当前关卡有未保存修改则保留它。

修订状态见 `Saved/GHS_CADRackRevision.json` 与 `Saved/GHS_CADRackVerification.json` 的 `success`。`Saved/GHS_NormalVerification.json`、`Saved/GHS_Normal_CaptureReport.json` 和 `Saved/GHS_Normal_UE_*.png` 是早期浅灰版记录，保留作历史。`baseline_hashes.json` 记录初次创建浅灰场景前的旧资产哈希。

绿色特效修订见 `Saved/GHS_NormalGreenFX.json`；`Scripts/ghs/capture_normal_green_fx.py` 输出 AGV 扩散和扫描的 UE 近景。34 个扩散与 6 个雷达仅修改独立材质参数，Time/Speed/Phase 动画及场景照明保持一致。首次生成及更新现有父材质都会读取上述配色配置。

历史高度修订曾将两场景建筑墙统一升至5.6 m，见 `Saved/GHS_WallHeightVerification.json`。本轮CAD货架修订将展示包络继续同步到9.6 m；共享配置仍为 `SourceAssets/GHS/wall_height_profile.json`，新旧备份及SHA由CAD货架修订报告记录，旧高度报告不覆盖。
