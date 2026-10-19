# 电动堆高车 HUD

`GHS_CAD_NormalWarehouse` 中 12 台 `GHN_FloorStacker_01` 至 `12` 已接入与装卸车共用的屏幕 HUD。身份来自 `NormalWarehouseFloorStacker` 与 `TwinId=GHN_FloorStacker_XX` 标签，不依赖编辑器对象名称。

标签高度 34，显示设备编号、文字状态、电量和独立的“演示”标记；详情为 320×184，显示剩余电量、货叉高度、所在区域及任务。堆高车使用门架/货叉图标，状态用文字和颜色区分：运行绿色、待机蓝色、预警琥珀色、故障红色、离线灰色。离线电量、货叉高度和任务显示未知，不沿用旧数值。

为便于展示，首次发现堆高车时填入固定演示数据：01 运行、02 待机、03 预警、04 故障、05 离线，其余设备分布这些状态。演示仅初始化一次；接入真实数据后，定时发现设备不会覆盖数据。场景保存的仅为稳定身份标签，状态演示在运行时初始化。

聚合沿用 Warehouse Camera → HUD 聚合最小臂长，默认 10000 cm。当前臂长低于阈值时逐台显示，达到阈值时按实际视口 2×2 分区，并在每个区域内按设备类型独立聚合：装卸车只与装卸车成组，堆高车只与堆高车成组。同一区域可以同时有一个装卸车标签和一个堆高车标签，每类最多四个、合计最多八个活动标签。组名称和图标始终对应本类设备，成员列表仅包含同类型成员；状态及演示标识独立显示，聚合标签保留组内最高级别的故障/预警提示。

四等分只决定成员归属，不约束标签位置。每个组使用本组成员真实投影点的平均值作为锚点，标签自然位置为 `Anchor - (标签宽度/2, 50)`，仅在整个视口边缘做限制，不再推入象限或固定上下分带。聚合标签首次相互遮挡时，按自然上下顺序做一次局部排布，在自然位置上下 40 逻辑像素内取所需的最小移动；自然高度相同则装卸车优先在上。这也覆盖跨区或同类型标签的遮挡，但不会合并它们的成员。额外位移每组最多 40 逻辑像素，并锁定到该组的稳定 key。其他标签消失或重新进入不会改动已锁定且仍存活的 key，也不逐帧累计避让；该组自身成员改变后形成新 key。近景逐台显示沿用原有设备跟随和视口边缘限制。

工程边界：若设备极密、已锁定标签与 ±40 像素范围内没有可行排布，则保留当前局部位置，优先避免将标签远推离设备，不扩大偏移上限。

聚合与拆分改为 120 ms 原位淡出/目标位置淡入，进入位移 6 逻辑像素，跟随滞后上限 8 像素。标签不再从各个车辆位置横穿屏幕汇入中心。列表及详情继续使用 220 ms 开合过渡，大距离重定位就地重新展开。

## 数据接入

从 `GHSWarehousePlayerController.TruckHUDWidget`（保留原接口名称）调用：

- `GetStackerData("STACKER-01")` 获取 `GHSStackerDataComponent`。
- `SetTelemetry(82, 180, Running, "T-0301", false)` 更新电量百分比、货叉高度厘米、状态、任务及演示标记。这里数值仅为调用示例。
- `SetTelemetry(-1, -1, Offline, "", false)` 标记离线并清空数值。
- `SelectEquipmentById("STACKER-01")` 与 `GetSelectedEquipmentId()` 管理通用设备选择。
- `GetRegisteredStackerCount()`、`GetRegisteredEquipmentCount()` 返回堆高车数及设备总数。

电量范围 0–100，货叉高度为有限非负数；非法输入返回 false 且完整保留旧状态。真实数据接入方负责断线/超时通知。`GetVisibleLabels().EquipmentIds` 为统一身份列表；旧 `TruckIds` 字段兼容保留，同样包含所有设备身份。`GetTruckData` 和 `SelectTruckById` 仍仅接受装卸车。

## 验证

2026-10-19 当前真实锚点与连续局部排布版本：Editor 编译退出码为 0；`Saved/Automation/HUDAnchorProximity/index.json` 于 14:57:57 记录 44 项 GHS 自动化全部通过，0 失败、0 警告。真实运行 Full（14:58:00）、Narrow（14:58:20）、LowAngle（14:58:40 后）均为 `success: true`，各通过 28 项检查，`assets_saved: false`；报告为 `Saved/GHS_StackerHUD_Runtime_Full.json`、`Saved/GHS_StackerHUD_Runtime_Narrow.json` 和 `Saved/GHS_StackerHUD_Runtime_LowAngle.json`。检查覆盖真实组中心定位、±40 像素上限、同类及跨区标签局部排布、存活 key 稳定，以及状态、点击和动画回归。已查看三种实景截图，低角度与窄屏标签均可见、未重叠并贴近设备；低角度截图为 `Saved/GHS_StackerHUD_SeparateTypesWide_LowAngle.png`。尚未进行完整打包构建。

2026-10-19 历史固定分带版本（位置方案已撤销）：Editor 编译退出码为 0；`Saved/Automation/HUDSeparateTypes/index.json` 于 14:33:50 记录 40 项 GHS 自动化全部通过，失败和警告均为 0。真实 Full 1920×1080（14:34:00）与 Narrow 360×800（14:34:20）运行报告均为 `success: true`，各通过 28 项检查，`assets_saved: false`。这些检查验证了当时的固定分带规则，但用户截图指出其将标签推离设备，属于错误的位置方案；旧通过结果不代表当前定位要求已经满足。编辑器于 14:34:36 恢复时确认了原场景、12 台堆高车和 10000 cm 阈值。尚未进行完整打包构建。

以下为更早的首次接入及混合聚合版本历史记录。

2026-10-19 历史首次接入版本：使用 MSVC 14.38.33130 编译 Editor 成功；35 项 GHS 自动化全部通过，报告 `Saved/Automation/StackerHUD/index.json`。真实 Full 1920×1080 和 Narrow 360×800 各通过 26 项检查，覆盖 64 台设备身份、五种状态、当时的混合四等分、近景逐台显示、实际点击、详情开合、120 ms 局部动画、实时数据替换、离线清空和重新发现保护。另完成装卸车 Full 的 20 项遥测/点击回归，仅在该测试进程隐藏堆高车。

实际截图已核验五种状态和窄屏布局，“演示”与状态同时可见。状态对照图为 `Design/GHS_Warehouse_HUD/exports/stacker-runtime-states.png`。Pencil 第四画板同步并保存快速聚合规则。尚未进行完整打包构建。

原生自动化直接验证 NaN、Inf 拒绝。UE Python 桥接会将 NaN 转换为 0，运行脚本先检测该转换，避免把桥接后的有效零值误报为组件接受 NaN；正常范围错误与离线恢复仍由真实运行测试覆盖。

运行 `Scripts/ghs/verify_stacker_hud_runtime.py`，Full 参数 `-ResX=1920 -ResY=1080`，Narrow 参数 `-StackerHUDNarrow -ResX=360 -ResY=800`，均搭配 `-game -RenderOffscreen -windowed -ForceRes`。脚本不会保存测试状态到场景。
