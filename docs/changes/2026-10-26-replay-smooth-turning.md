# 追溯叉车转向连续性

## 行为

- 保持原行驶速度：载货 2.6m/s，空载 3.2m/s；不加入入弯减速、加减速曲线或额外等待。
- 在现有障碍物净空约束内，将行驶圆弧半径从 0.85m 调整为 1.50m，路径弦采样从 0.35m 细化到 0.10m。
- 对展开后的车头角度做 0.30 秒对称时间窗平均，再用保形三次插值连接。提前轻微转向，平滑进入和退出圆弧，保留路线端点朝向与取放货对位。
- 离线烘焙朝向关键帧，运行时沿用按绝对时间采样。暂停、拖动、倒查和倍率播放不依赖上一帧，也没有逐帧寻路或物理计算。
- 合并可按时间精确重建的冗余帧；原路径拐点保留，附加时间窗采样避开微秒级近邻节点，防止 JSON 时间精度导致速度误差。角度压缩跨度保持小于 180°，兼容运行端最短角插值。
- 仍为 5 辆人工叉车、3 辆装卸卡车、10 个货物、48 个事件；故障暂停仍为 45 秒。完整循环随略短的圆弧路程更新为 2461 秒。

## 涉及文件

- `Scripts/ghs/replay_plan_routes.py`：路径半径与圆弧采样。
- `Scripts/ghs/replay_motion_profile.py`：匀速运动与连续朝向的离线烘焙。
- `Scripts/ghs/replay_build_timeline.py`：仅叉车接入新朝向曲线，沿用原调度和货物交接。
- `Content/GHSTwinUI/data/order-replay.json`：重新生成的项目实际回放数据。
- `Scripts/ghs/tests/test_replay_motion_profile.py`：匀速、时间、角度连续、短段、跨角、压缩与时间精度回归。
- `Scripts/ghs/replay_validate_turning.py`：对实际导出数据检查原行驶速度和转向采样。
- `Scripts/ghs/verify_replay_smooth_turning.py`：独立 UE 游戏实例中检查载货过弯、跟随、回放寻址、货物事件和场景恢复。

## 验证入口

使用 UE 内置 Python 运行单测、时间线与导出转向检查；几何检查使用 Blender 5.2 的 Python 3.13，与现有 NumPy/Shapely 依赖版本一致。

```text
python -B -m unittest discover -s Scripts/ghs/tests -v
python -B Scripts/ghs/replay_validate_turning.py
python -B Scripts/ghs/replay_validate_timeline.py
python -B Scripts/ghs/replay_validate_static_actions.py
python -B Scripts/ghs/replay_validate_forklift_fx.py
```

真实渲染验证使用 `-game -RenderOffscreen -TwinDiagnostics` 独立实例执行 `verify_replay_smooth_turning.py`。结果和截图位于 `Saved/OrderReplay/SmoothTurning-20261026/`，不保存或覆盖用户关卡。

## 本次验证结果

- 11 项单元测试通过，包括对称朝向过渡、恒速与导出时间精度回归；独立代码复核通过。
- 实际数据所有行驶段相对原速度的最大误差为 0.002827m/s，处于既定 0.005m/s 导出容差内。最大转向角速度约 122.46°/s；转向变缓来自更大的圆弧与连续朝向，不来自降低行驶速度。
- 静态扫掠检查 63,337 个独立叉车姿态、14,382 个障碍物几何，零碰撞；8 辆车辆的动态扫掠与货物归属连续性检查通过。
- 实际 C++ 轨迹构建及剩余路径验证通过：5 个轨迹组件、8,265 个实例，单次路径构建约 62.1ms。运行时实例数量固定。
- 独立 UE 渲染验证 6 项通过，记录入弯、弯中、出弯、取货和放货截图。载货过弯实际采样速度为 2.5966–2.6001m/s（跨弯段两端直线距离测量）；暂停/反向寻址、跟随、故障恢复、循环和退出恢复通过。
- 本机此次启动回放调用约 453ms，含屋顶和相机准备约 1.031s；这是单次测量，不是多机性能保证。没有新增逐帧规划。
- 关卡与轨迹材质 SHA256 均与修改前一致。最终回放数据 SHA256：`5274f34ca8afe5f0cf267388727b95da414c3c94c0fd0a1fc6d6de7aa390b121`，单车最大 14,929 个关键帧。

本次不修改场景地图、轨迹材质、UI 设计稿或 Windows 发行包。项目下一次开启追溯会加载更新的数据；已有发行包需要重新打包才会包含此改动。
