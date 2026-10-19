# 人工叉车 HUD

实现文件为 `GHSMannedForkliftDataComponent`、`GHSMannedForkliftIdentityLibrary` 与现有 `GHSDockTruckHUDWidget`。仅由 `GHS_CAD_NormalWarehouse` 当前控制器创建。运行时发现当前场景中的独立车辆并核对身份，实际注册数量随场景变化，不恢复用户删除的车辆。

自动识别仅接受使用以下完整网格路径的独立 `StaticMeshActor`：`/Game/GHSNormalWarehouse/MannedForklift/Meshes/SM_GHN_MannedForklift50k.SM_GHN_MannedForklift50k`。直接拖入这份网格，即使没有标签，也会在运行时发现阶段补齐 `NormalWarehouseMannedForklift` 和唯一 `TwinId=GHN_MannedForklift_01` 形式的标签。复制导致身份重复时自动分配新编号，无需手动修改 TwinId；车辆位置、旋转与缩放不变。其他网格、ISM/HISM 批量实例，以及带其他设备 TwinId 的对象不参与人工叉车身份分配。

显示身份为 `FORK-01`，与堆高车身份分开；标签编号不从编辑器显示名称推断。移动、复制或删除普通独立 StaticMeshActor 即可调整布置。已建立身份的原车保留编号，复制件获得新编号；编号分配记录已使用的上限，不依靠压缩编号来填补删除车辆留下的空号。

当前 16 台人工叉车的唯一 TwinId 已随编辑器关卡保存。以后在 PIE 或独立运行中自动生成的新编号只存在于运行世界，不会自动保存回编辑器。需要用于后端绑定的稳定编号时，在编辑器世界调用 `GHSMannedForkliftIdentityLibrary.reconcile_world`，检查分配结果后显式保存关卡。此函数只核对身份，不改变车辆变换；在编辑器世界会把相关关卡标记为未保存，但不自行保存资产。

```python
import unreal

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
changed = unreal.GHSMannedForkliftIdentityLibrary.reconcile_world(world)
# 检查标签与编号后，显式保存当前关卡。
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
```

上述调用应在编辑器打开目标仓库关卡、且本轮 C++ 模块已编译加载后执行；不要把 PIE 世界中的临时编号当作已持久化的后端编号。

常驻标签高 34 px，显示有人驾驶叉车图标、编号、状态、载荷与独立“演示”标记；详情为 320×184 px，显示当前载荷 t、行驶速度 km/h、驾驶员工号、区域、任务及连接时间。采用批准设计的银白卡片、深灰蓝文字与工业蓝识别。没有假定电动或燃油动力，也没有把设计中的 2.0 t 额定值当成实际设备规格。

人工叉车独立使用 `MannedForklift` 聚合类别，与 `DockTruck`、`Stacker` 分开；每类按当前屏幕 2×2 分区最多四组，三类最多十二组。聚合仅决定成员归属，位置继续贴近本组真实投影中心，沿用最多 ±40 px 的局部避让、120 ms 标签聚合/拆分和 220 ms 详情/列表开合。列表宽 260 px，每页五台。通用选择和旧装卸车/堆高车接口保留。

## 数据接口

从 `GHSWarehousePlayerController.TruckHUDWidget` 获取：

- `GetMannedForkliftData("FORK-01")` 返回该车 `GHSMannedForkliftDataComponent`。
- `GetRegisteredMannedForkliftCount()` 返回实际人工叉车数量。
- `GetRegisteredEquipmentCount()` 返回三类设备总数。
- `SelectEquipmentById("FORK-01")` 选择并展开详情；`GetVisibleLabels().EquipmentIds` 包含统一设备身份。

组件接口：

```cpp
bool SetTelemetry(float Load, float Speed, EGHSMannedForkliftStatus NewStatus,
    const FString& NewDriverId, const FString& NewArea, const FString& NewTaskId,
    const FString& NewReason, bool bDemoData = false);
```

Load 单位为吨，Speed 单位为 km/h；运行、待机、预警要求两者都是有限非负数。故障、离线和待接入还接受 `(-1,-1)`，并清空两项指标为未知。离线和待接入额外清空驾驶员、区域和任务；故障仅保留本次更新明确提供的这些字段与故障原因。非法更新整条拒绝，不改变此前数据。真实接入方负责断线/超时通知。

`LastUpdateSeconds` 为最近一次接受更新的游戏时间；`LastOnlineSeconds` 为最近一次在线更新的游戏时间，首次离线保持 `-1` 未知。详情显示连接数据的真实时间差；演示场景始终显示“演示数据 · 非实时”或“演示数据 · 离线”，不伪造连接时间。

首次发现人工叉车时加载固定设计样本：01 运行、02 待机、03 预警、04 故障、05 离线、06 运行、07 待机、08 运行。人员、区域、任务和数值均是明确标记的演示数据。演示只初始化一次，真实更新之后定时重新发现不会覆盖数据；手动预置组件也不会被自动填充演示。任务系统尚未连接，因此详情展示任务摘要和编号，不提供无效跳转按钮。

## 历史验证：首次 8 台人工叉车

以下为 2026-10-19 首次 8 台人工叉车版本的历史结果，不代表本轮自动识别、复制身份修复和 16 台场景的编译或运行验证：TestEditor 编译通过；50 项 GHS 原生自动化全部通过，无失败或警告。覆盖身份、合法及非法遥测、NaN/Inf、故障/离线清空和恢复、演示初始化保护、三类独立聚合，以及第三类进入已有两类标签时的局部重排。

该次离屏运行在当时保存的 Normal 仓库验证了 52 辆装卸车、9 台堆高车和 8 台人工叉车；三类独立聚合、真实点击列表/详情、五种人工叉车状态、旧两类选择、实时更新后重新发现保护、离线未知清空均通过。这些是历史数量，不用于重建当前车辆。数值与任务仍为明确标记的演示样本，没有接入设备后端。

首批 8 台人工叉车位于 `GHS_Normal/Vehicles/MannedForklifts`，标签编号为 `GHN_MannedForklift_01` 至 `08`。使用共享网格 `/Game/GHSNormalWarehouse/MannedForklift/Meshes/SM_GHN_MannedForklift50k`，保持 1:1 尺度，含货叉长 3.448 m、宽 1.249 m、高 2.337 m。UE 导入清理后的四级 LOD 为 49,661 / 24,830 / 12,415 / 5,960 三角面。首批布置以完整车辆包围盒验证至少 0.5 m 车货间隔，南北后方 2 m、中间通道 2.5 m 空带通过当时的墙体、地面及现场障碍检查。

证据：`Saved/GHS_MannedForkliftFleetImport.json`、`Saved/GHS_MannedForkliftHUD_Runtime_Full.json`、`Saved/Automation/MannedForkliftHUD/index.json`。备份：`Saved/Backups/GHS_MannedFleet_20261019_165836`，包含导入前后和编译前保存状态。

## 本轮场景修复：当前 16 台人工叉车

`Saved/GHS_ManualForkliftFollowup.json` 已记录 `success: true`：保留原有 12 台人工叉车，其中 4 台用户复制件的重复 TwinId 修复为 `09` 至 `12`；新增 `13` 至 `16` 四台，分别补充东中、西中、中央和西北地堆作业区域。当前人工叉车总数为 16，场景 Actor 总数从 244 增至 248。全部已有 Actor 的位置、旋转与缩放保持不变，仅这 4 台复制件的标签发生变更；没有恢复用户已删除的堆高车。当前规划快照为 52 辆装卸车、6 台堆高车、32 台 AGV 和原有 12 台人工叉车。

新增车辆沿用同一共享网格和 1:1 尺度，完整包围盒包含货叉及驾驶员。现场检查覆盖 9,968 个障碍实例、9,013 个墙体三角形包围盒；每辆车及保留通道均检查实际地面覆盖，车辆使用 9 个采样点。新增车辆与货堆的最近间隔为约 0.5 m，三处中央位置保留 2.5 m 通道，西北位置保留 2 m 通道；现场报告中的四处 `passage_live_validated` 均为 `true`。离线规划还验证新增车辆距任何原有车辆至少约 16.35 m，新增车辆之间至少约 45.38 m。这些新增点位的检查不等同于重新认证用户自行移动的所有旧车位置。

本轮证据：`Saved/GHS_ManualForkliftFollowup.json`、`Saved/GHS_ManualForkliftAdditionsPlan.json`、`Saved/GHS_ManualFollowupProbe.json`。备份：`Saved/Backups/GHS_ManualFollowup_20261019_174253`。场景修复报告确认只修改 `Content/Maps/GHS_CAD_NormalWarehouse.umap`，保存后 SHA-256 为 `a6294843e0df1009038c5fc3e0e38dd6b7986c6f5449b5d6834350cb12c11d67`。

本轮最终 TestEditor 编译通过，55 项 GHS 原生自动化通过，0 失败、0 警告。离屏运行通过 16 台独立注册、原 12 台位置保留、4 台新增点位、分组列表及点击详情；临时生成无标签模型与复制编号车辆，分别自动分配 FORK-17、18，删除后再生成分配 FORK-19，没有复用删除编号或改写原车实时数据。截图已检查，HUD 仍使用原人工叉车设计。场景演示值尚未连接设备后端。

16 台车辆的编号归属及编号高水位已显式保存到编辑器地图，变换、材质、其他模型均保持原样。最终地图 SHA-256 为 `f7201ef820bcfca947071a5e936427362a0c002ba50398dba2e17755d7e40066`。证据：`Saved/GHS_ManualForkliftIdentityPersisted.json`、`Saved/GHS_ManualForkliftFollowup_Runtime.json`、`Saved/Automation/ManualFollowup/index.json`；运行测试不保存临时车辆或任何资产。
