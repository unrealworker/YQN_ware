# MPR 主仓储标签、屋顶溶解与 GHS 相机验收

现有 `/Game/Maps/MPR_CAD_Warehouse_B50B57` 直接复用 GHS 相机、控制器和主仓储标签绘制逻辑。
点击“ MPR · 主仓储”或主仓屋顶启动同款扫描溶解，点击时保持当前相机；右下复位或 Home 恢复屋顶并返回目录配置的 MPR 入口视角。旋转、平移、滚轮与缩放按钮沿用 GHS 输入逻辑。

屋顶组包括 4 个屋面、16 个边缘、5 组光伏、4 组实例化天窗和 1 组 HVAC，共 30 个 Actor。所有部件共用一个扫描时钟；正常开启 0.8 秒、关闭 0.55 秒。6 个新增私有扫描材质复用 GHS shader，并保留原材质参数；停止、复位和卸载恢复原材质与可见性。

MPR 使用 `roof-inspection` 功能，不加载 GHS 业务浏览器、设备标签、库容和交通模拟。直接开图和从地球进入使用同一入口配置；`-MPRProfile` 保持原静态验收模式。

## 验证结果

- UE 5.8 TestEditor Development 完整构建成功。
- 本次屋顶、相机、布局、目录和恢复逻辑相关 43 项自动化测试全部通过，0 错误、0 警告。完整路径和原始报告校验和见 `automation_summary.json`。
- 同次全套运行共 164 项，162 成功、2 失败。失败为共享工作区另一任务尚未生成国家标签材质、地球网格尚未启用 CPU Access；不计为本任务通过，也不宣称全套通过。
- `runtime_validation.json`：在实际 MPR 游戏场景调用标签点击路径，验证 30 个部件同步溶解、全程固定相机、原材质恢复、GHS 旋转/平移/缩放/复位，以及地图与来源材质未改变。
- `globe_runtime_validation.json`：实际执行两轮地球→MPR→开顶→返回，验证共用持久相机、MPR 入场姿态与直接进入一致、屋顶 Actor 卸载和下次进入状态重建。
- 已人工查看下面四张 1920×1080 固定镜头截图。中间扫描图仅为取帧减慢游戏时钟，动画耗时由正常速度另行验证。

| 状态 | 实测动画耗时 / 平均 FPS | 证据 |
| --- | --- | --- |
| 闭顶 | 121.27 FPS | `01_closed.png`、`closed_native.csv.gz` |
| 扫描中 | 正常开启 0.81 秒 | `02_mid_scan.png` |
| 完全打开 | 87.77 FPS | `03_open.png`、`open_native.csv.gz` |
| 复位 | 正常关闭 0.56 秒 | `04_restored.png` |

FPS 来自本机 UE5.8 独立 editor-game、RenderOffscreen、1920×1080、不限帧，预热后各采集约 15 秒原生 CSV；GPU 时间列已验证。不是打包版或 Pixel Streaming 性能承诺。

## 保留项

未修改地图、原屋顶材质、模型、光伏布局和场地。地图 SHA256：`4dd68cb727c4a87a473cb65baa7abeaf7793409f73cb7620100d650033f27b75`。
`material_validation.json` 记录新增 6 个材质资产及生成时 1884 个已有 Content 包均未改变的核验。

## 可复核入口

- 材质：`Tools/MPRWarehouse/prepare_mpr_roof_scan.py`（受生成前资产快照保护的单次生成工具）。
- 直接进入：`Tools/MPRWarehouse/verify_mpr_roof_interaction.py`。
- 地球进出：`Tools/MPRWarehouse/verify_mpr_globe_interaction.py`，读取前一项成功报告以核对入口相机。
- 两项运行验证均在自有进程中使用 `-own -game -RenderOffscreen -TwinDiagnostics -ForceRes -ResX=1920 -ResY=1080 -EnablePython`，通过 `-ExecCmds="py <脚本绝对路径>"` 执行，结束后退出，不保存关卡资产。
