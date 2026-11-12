# MPR 中央传送装置运动拖影修复

原关卡 `/Game/Maps/MPR_CAD_Warehouse_B50B57`，固定相机、1920×1080，设备在原生 Tick 中持续运行，截图写入期间也保持运动。

## 原因与修改

- 中央立柱、托盘和包裹每帧调用 `MarkRenderStateDirty`，反复销毁重建渲染状态。
- 实例相对固定组件运动，却未向 GPU Scene 提供实例前帧矩阵，导致 TSR 历史重投影出现大面积蓝白拖影。
- 使用批量 current/previous 实例变换更新，保持渲染代理稳定；继续使用 TSR（`r.AntiAliasingMethod=4`）。
- 首次显示、隐藏、槽位换包、重置和实例池重建清理历史。同一引擎帧内多次提交保留上一渲染帧位置。暂停时提交静止位置，清除残留速度。
- 只修改中央三种动态组件的表现层，固定步长分拣逻辑、场景、材质及灯光不变。

## 验证

- TestEditor Development 编译成功；27 项 MPR 自动化测试全部通过，新增 3 项测试直接读取 UE ISM 的 current/previous 矩阵。
- `before_moving_tsr.png` 复现原问题；`after_moving_tsr.png` 在相同镜头与 TSR 下消除中央立柱、托盘上的大面积拖影。设备相位随实时运行略有不同。
- `baseline_fxaa_diagnostic.png` 仅用于定位时域问题；没有把 FXAA 写入项目设置。
- 前后各 8 张截图包含持续运动、暂停、FXAA 对照、速度缓冲和恢复 TSR。每张运动截图都验证原生实例在采集期间位移，暂停图验证静止。
- 1080p、60 FPS 上限、TSR 下采集 900 个原生帧，约 15.25 秒，平均 59.03 FPS。GPU 平均 7.49 ms；帧时间 P95 16.67 ms。完整采样保留了 1 帧 262.25 ms 的峰值，未删异常帧；该样本不代表无卡顿承诺或串流性能。
- 1943 个 Content 包哈希保持一致，原关卡和编辑器相机已恢复。用户原有未提交场景及配置修改保留。

完整数据见 `baseline_report.json`、`fixed_report.json`、`automation.json`、`native_frames.csv` 与 `scene_preservation.json`。

## 重现入口

使用 `Tools/MPRWarehouse/verify_mpr_temporal_render.py` 在独立原生游戏进程运行，指定原 MPR 关卡及 `-game -RenderOffscreen -TwinDiagnostics -EnablePython -ForceRes -ResX=1920 -ResY=1080`。
`-MPRTemporalBaseline` 标记基线，`-MPRTemporalVelocity` 增加速度缓冲截图。
