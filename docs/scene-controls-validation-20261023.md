# 场景图层与库容验收 · 2026-10-23

本次实现已批准的四图层即时控制、货架80%/地堆100%默认展示比例，以及 Glen Helen 延长道路两处横向端帽移除。开启色统一为 `#356BFA`。比例只影响场景货物，不写业务库存；原始数据未核验提示保留。

## 实现边界

- 建筑外壳、货架与货物、作业设备、POI 独立控制。关闭建筑先完成已有0.5秒开顶，再隐藏外墙；闭顶与开顶期间保持内部标签及拾取锁定。
- 库容按完整槽位稳定筛选，0%保留货架钢结构，地堆双托盘整组显隐。隐藏货物不命中，隐藏当前选择清除详情。材质、所有LOD和CPU命中共用槽位规则。
- 连续滑动合并为不超过30Hz的中间更新，松手立即发送最终值。13组HISM、实例数量/变换不重建，只更新7个共享材质实例参数。
- 恢复默认保留相机和屋顶状态；全仓复位恢复外壳/屋顶，保留其他图层与比例。主动设备定位恢复设备层，开顶后再定位。快速切换以最后目标为准。
- 车流保留既有32实例池。修改仅覆盖目标场景，原始CAD地图、用户地面材质、业务数据与无关资产保留。

## 检查结果

| 检查 | 结果 / 证据 |
| --- | --- |
| UE 5.4 TestEditor / TestGame Development | 编译通过；指定MSVC14.38.33130，日志在 `Saved/SceneControls/build-editor.log` 和 `build-game-final.log` |
| UE原生自动化 | 114通过、0失败；`Saved/Automation/SceneControls/index.json` |
| Web测试 | 85通过、0失败；`Saved/SceneControls/web-tests.log` |
| 完整槽位及LOD | 25,056货架槽位、7,530地堆组；40个LOD均保留完整货箱/托盘，修正9个LOD3远景丢托盘问题；`capacity-lod-slots.json`、`capacity-lod-fix.json` |
| 导入及场景保护 | 保存成功、370 Actor；原材质、地堆网格、实例顺序/变换与无关场景比较一致；`assets-apply.json`、`capacity-apply.json`、`RoadEndcaps/apply.json` |
| 实际UE运行 | `Saved/SceneControls/Runtime/20261022_190906/runtime.json`，success=true，78.063秒 |
| 道路开口 | 两端实景已检查，横挡移除、侧沿保留；同目录06/07 PNG |
| 货物及阴影近景 | `Saved/SceneControls/Closeups/20261022_191447/closeups.json`，success=true；rack/floor各100→0同机位对比，双蓝托盘清楚可见、货物块状阴影随0%消失，钢架及细杆阴影保留 |
| 编辑器恢复 | `Saved/SceneControls/editor-restored.json`，success=true，370 Actor，原相机和选中对象已恢复 |

所有相对证据路径均以项目根目录为基准；省略目录的容量/道路报告位于 `Saved/SceneControls`。运行时检查包含四开关蓝色、默认比例、禁用数值保留、重置取消待发输入、快速外壳反向切换、业务刷新不重显隐藏层、隐藏选择清理、定位恢复、旧定位取消、0/默认/100槽位和同一射线隐藏后拒绝命中。

## 本机性能采样

RTX 5060 Laptop GPU，1920×1080、100%渲染比例，独立UE游戏进程；固定相机、图层、车流和渲染设置。关闭帧率上限/VSync采样，采样结束恢复CVar。每状态约10秒，保留采样边界与所有长帧，不删除异常值。实际UE CSVProfiler的GPU时间有效；不是以Python/Slate计时冒充GPU指标。

| 状态 | 平均帧时 ms | P95 ms | Game ms | Render ms | GPU ms | >50ms帧 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 默认80% / 100% | 16.220 | 17.279 | 2.040 | 15.945 | 16.018 | 0 |
| 空库0% / 0% | 16.288 | 17.154 | 2.013 | 16.033 | 16.097 | 0 |
| 满库100% / 100% | 16.412 | 17.204 | 2.058 | 16.146 | 16.231 | 0 |
| 连续滑动 | 16.789 | 18.118 | 2.927 | 16.498 | 16.596 | 0 |

拖动10秒触发2,500次CEF输入，合并为250次原生容量更新；初始化扫描仍为1次，Actor、HISM数量及实例变换不变。相对默认平均帧时增加0.569ms，P95增加0.839ms，最长帧26.249ms。本次采样未观察到明显长帧；这是本机单轮局部检查，不是固定60FPS保证或服务器多会话/像素流验收。

原始CSV在 `Saved/Profiling/CSV/SceneCapacity_20261022_190906_*.csv`，其SHA256与完整统计记录在运行报告。功能输入由真实CEF DOM事件驱动，不表示已验证物理鼠标端到端延迟。

复验使用独立进程：`UnrealEditor.exe Test.uproject /Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory -game -RenderOffscreen -TwinDiagnostics -windowed -ForceRes -ResX=1920 -ResY=1080 "-ExecCmds=py D:/UEPro/Test/Scripts/ghs/verify_scene_capacity_runtime.py"`。`-ForceRes`用于避免离屏窗口被桌面工作区自动缩小。脚本不保存资产，完成或失败时自行退出。不要与其他性能测试同时运行。

## 设计交付状态

35画板/42组件、四开关开启色和默认/禁用状态导出已经检查；原有30张非本轮画板指纹不变。设计索引与规范位于 `Design/GHS_Twin_SaaS_Concept`。

Pencil画布已更新，但Windows锁屏阻止原生保存。`Saas.pen`仍待解锁后保存；索引、README和验证记录明确标记此项未完成，不将PNG导出当作源文件已保存。

本次改动另已通过Pencil读取API保存为 `Design/GHS_Twin_SaaS_Concept/scene-controls-canvas-recovery.json`：425个唯一节点，缺失引用/图片均为0，供意外丢失画布时恢复。该备份不替代正式 `.pen`。
