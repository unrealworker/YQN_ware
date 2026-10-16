# GHS 视频风格仓库

新关卡：`/Game/Maps/GHS_CAD_NormalWarehouse`。

依据 `D:/DDDownload/normal_video.mp4` 的 6.44、9.20、25.76、28.56 秒画面，采用浅灰展示环境、银白货架、工业蓝托盘和层板、牛皮纸货箱。参考帧和联系表位于 `Reference/`。视频中的品牌片头及软件界面不属于仓库模型。

关卡继承已经核对的 GHS CAD 布局、厚墙、柱体、货架、货堆、KUKA AGV 和充电设备。原有物体位置、模型几何及 122 个柱旁避让货位保持一致。高度继续采用原场景的展示估算值。没有新增 CAD 未标明的输送线。

材质与特效均独立存放在 `/Game/GHSNormalWarehouse`，通过组件覆盖应用，不修改共享网格默认材质。`material_style.json` 和 `lighting_style.json` 保存本场景的配色及照明参数。AGV 雷达扫描与底部扩散保留 Time 驱动的动态 Decal，沿用原 GHS 绿色 `[0.04, 0.8, 0.30]`。浅色地面上使用 `OpacityScale=1.8`、`EmissionScale=0.12` 增强线条与拖尾，保持受控发光。

照明采用一盏方向光和一个固定环境立方体 SkyLight，无点光源阵列。固定曝光、低 bloom、受控 AO 提供明暗层次；继续使用 HISM 实例化。没有针对性能做未经测量的帧率承诺。

## 重建和验收

- `Scripts/ghs/build_normal_scene.py`：从保存的旧场景克隆并应用独立风格。
- `Scripts/ghs/verify_normal_scene.py`：在新的 UE 进程中重新加载关卡，核对 CAD 实例、实际包围盒相交、模型与材质、动态特效、光源以及旧 Content 文件哈希。
- `Scripts/ghs/capture_normal_scene.py`：输出四个相机视角的真实 UE 渲染，不保存场景或资产。
- `Scripts/ghs/open_normal_scene.py`：在当前 UE 编辑器打开新场景；如果当前关卡有未保存修改则保留它。

结果见 `Saved/GHS_NormalVerification.json`、`Saved/GHS_Normal_CaptureReport.json` 和 `Saved/GHS_Normal_UE_*.png`。`baseline_hashes.json` 记录本次工作开始前的旧资产哈希。

绿色特效修订见 `Saved/GHS_NormalGreenFX.json`；`Scripts/ghs/capture_normal_green_fx.py` 输出 AGV 扩散和扫描的 UE 近景。34 个扩散与 6 个雷达仅修改独立材质参数，Time/Speed/Phase 动画及场景照明保持一致。首次生成及更新现有父材质都会读取上述配色配置。

2026-10-16：按用户要求，两套场景的建筑墙统一升至 5.6 m，与柱顶齐平；墙顶轮廓同步到 5.6005 m。共享配置在 `SourceAssets/GHS/wall_height_profile.json`，同步验收见 `Saved/GHS_WallHeightVerification.json`。历史基线不覆盖，本次授权的地图/registry 变更由 `Saved/GHS_WallHeightSync.json` 的精确 before/after SHA 记录。
