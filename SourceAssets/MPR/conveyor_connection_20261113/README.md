# MPR 入库摆轮接驳修复

唯一来源是原 DXF 的 `2D457E / 入库摆轮05`。这套装置被旧的长平行线匹配器简化为 12 个矩形辊道实例，遗漏了中央连续输送带及左右五组分流喉口。原图右侧 `2D4587`、`2D45D9` 是独立输送线，本次不跨越通道连接它们。

`cad_evidence.json` 记录原文件 SHA256、实际 DXF 句柄、平面坐标及原始实体片段。斜接边界 `27F9DE` 与后续 `27FAA1` 都是 LINE；全块唯一 LWPOLYLINE `292259` 是设备旁控制矩形，没有 bulge。10727 个 ARC 的最大跨度为 0.116857 米，是轮子/五金局部轮廓。本次遵循图纸直线与斜线轮廓，不人为改成圆弧。接收框架 XY 来自 `289653`、`28969F`；原图没有高度尺寸，Z 沿用现有邻接辊道的 1.035 米承载面。

`replacement_targets.json` 将这一个 CAD 实体定位到两个原 HISM Actor 的 12 个实例。实际应用重新按 GUID、组件、网格和完整 transform 唯一匹配，旧索引仅作记录。导入独立的 `SM_MPR_CAD_2D457E_Connected`（13904 三角、1 实例），保留其他实例、Actor、材质、交互与所有原资产。

离线生成与验证：

```powershell
& 'D:/WinAPP/Blender/blender.exe' -b --python Tools/MPRWarehouse/build_conveyor_connection_20261113.py
& 'D:/UE/UE_5.8/Engine/Binaries/ThirdParty/Python3/Win64/python.exe' Tools/MPRWarehouse/verify_conveyor_connection_20261113.py
```

UE 使用原关卡 `/Game/Maps/MPR_CAD_Warehouse_B50B57`，在独立 owned commandlet 中依次运行同一个 `Tools/MPRWarehouse/apply_conveyor_connection_20261113.py`：

1. `-own -MPRConnectionDryRun`：只读核对当前 12 个实例，记录当前关卡哈希与 Actor 签名。
2. `-own -MPRConnectionApply`：要求基线未变；保存前比较所有非目标 Actor，保存后核对所有原 Content 资产。只允许原关卡文件变化及增加独立网格。
3. `-own`：独立重载，核对全部 Actor 签名、完整实例布局、世界设置、渲染属性与关卡哈希。

验证输出统一写入 `Saved/MPR/conveyor_connection_20261113/application`，只保留一套紧凑合同和结果，不创建逐帧图片。当前离线拓扑验证：原承载面 4 个连通分量，修复后 1 个；中央 1001 个采样点全部连通，10 个 CAD 分流出口和上游 `2D4DB8` 端点覆盖正确。

应用及独立重载已完成：仅修改两个原 HISM Actor 的 12 个目标实例，增加一个专用网格 Actor；922 个非目标 Actor 和 1975 个既有 Content 文件保持一致（原关卡文件是唯一允许变化的既有资产）。独立 UE 进程重载后，925 个 Actor 的完整签名和关卡哈希核对通过。详见 `apply_report.json`、`reload_report.json` 和 `verification_contract.json`。

`before.png`、`after.png` 为实际运行画面，均为 1920×1080、完全开顶、同一固定相机。相机实际位置约 `(-3500.012, 5937.314, 2099.469)` cm，yaw 0、pitch -48.72；精确姿态记录在 `before_view.json`、`after_view.json`。修复后中央主线、十个分流出口与上游入口连续，周边原有独立长输送线和工作台保留。没有输出逐帧序列。

原关卡 SHA256：`67cec0faee74dd8f38e7c74c4b305aa9bd2dc0c7558efc1ed131bc4ad034a659`；保存及重载后的 SHA256：`b05af822f27a1a973abf12afb8e6fd9776b620ca53c10d6525e2fa3dc921142f`。
