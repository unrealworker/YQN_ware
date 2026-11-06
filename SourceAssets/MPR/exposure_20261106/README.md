# MPR 开顶场景亮度修正

在现有 `MPR_CAD_Warehouse_B50B57` 上，将 `MPR4_ReferenceStyle` 固定 EV100 从 **-0.1 调到 0.6**，曝光降低 **0.7 档**，缓解大面积地面、白色货架与货物偏亮的问题。保留原灯光方向、强度、阴影、蓝白配色、GHS 相机和屋顶交互。

之前为室外提亮时，太阳从 3.8 提至 5.0 lux，固定 EV100 从 0.3 降至 -0.1。白色结构和浅灰地坪本身反照率较高，开顶后直射区域显得泛白。Bloom 已关闭，相机没有后处理曝光覆盖。本次只修正 MPR 自身曝光，不修改共用的 GHS 材质。

## 验收

- 在实际 UE 渲染中比较固定 EV100 -0.1、0.35、0.6，选择 0.6。
- 保存前后完整核对 **855 个 Actor**：唯一变化是该后处理体的 `AutoExposureMinBrightness`、`AutoExposureMaxBrightness`，两者均为 0.6；模型、实例、材质引用、相机和灯光参数均保持原样。
- **1074 个 MPR / GHS 材质及模型资产文件**校验和保持一致。
- 独立重新加载关卡验证通过，固定曝光正确持久化；再启动实际游戏验证闭顶、开顶和近景。
- 下列三组截图均为 **1920×1080**，前后相机姿态一致。额外分拣区近景见 `after_sorter_detail.png`。

| 镜头 | 修改前 | 修改后 |
| --- | --- | --- |
| 闭顶园区 | `before_exterior.png` | `after_exterior.png` |
| 开顶整体 | `before_open_overview.png` | `after_open_overview.png` |
| 室内货架 | `before_interior.png` | `after_interior.png` |

分拣区近景实测 **57.41 FPS**，原生 CSV 861 帧／约 15 秒，平均帧时间 17.42 ms。本次用户的 UE 编辑器同时运行，且采用室内近景；不能与上轮独立运行的园区概览帧率直接比较。原始数据保存在 `interior_native.csv.gz`，完整指标见 `runtime_validation.json`。

`apply_validation.json` 与 `reload_validation.json` 保存修改范围和加载核验。`before.json.gz` / `after.json.gz` 为场景状态快照。`comparison_validation.json` 保存三档试验记录。

关卡修改前 SHA256：`4dd68cb727c4a87a473cb65baa7abeaf7793409f73cb7620100d650033f27b75`。
修改后 SHA256：`0dee9e0dce26371c768cc6611d7d1fb1d9327412a9605951b4372b35b5858dd0`。

应用与独立加载核验入口为 `Tools/MPRWarehouse/apply_mpr_exposure.py`，在自有 `-run=pythonscript` commandlet 执行，核验增加 `-MPRExposureReload`。运行截图入口为 `Tools/MPRWarehouse/capture_mpr_exposure.py`，使用 `-own -game -RenderOffscreen -TwinDiagnostics -MPRExposureVerify -ForceRes -ResX=1920 -ResY=1080 -EnablePython`。所有验证进程均已退出，用户当前编辑器与正在运行的关卡未切换。
