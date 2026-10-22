# 场景库容资产

这组资产为 Zcool 仓库提供货架、地堆两条场景库容滑条。默认货架 80%、地堆 100%；只改变货物展示和可选中状态，不写入业务库存、库位状态或设备遥测。

10 个 `SM_GHS_V2Rack_*_Capacity.fbx` 来自 `SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json` 的完整货架几何，由 `Scripts/ghs/build_storage_capacity.py` 复用原货架/独立纸箱构建器生成。每个导出网格的三角数与完整源模型一致，钢架几何签名、尺寸和位置保持一致。`_Occ70` 只可能是导入前场景使用的旧网格，不是本组资产的货物数量基准。

`Content/GHSTwinUI/data/scene-bindings.json` 提供实际场景分组与实例顺序。排除其重复的 `_Occ70` 映射后，10 组货架共 1,629 个实例、25,056 个完整货物槽位。3 组地堆共 7,530 个实例，继续使用 `/Game/GHSZcoolSmartFactory/DoublePallet/Meshes/` 中的双托盘网格；每个双托盘实例作为一个整体显示或隐藏，不重新生成、拆分或缩放地堆几何。

| 容量状态 | 货架可见槽位 | 地堆可见整组 |
| --- | ---: | ---: |
| 0% / 0% | 0，钢架保留 | 0 |
| 默认 80% / 100% | 20,045 | 7,530 |
| 100% / 100% | 25,056 | 7,530 |

`storage_capacity.json` 保存源文件 SHA-256、完整几何描述、实际导出的 FBX 校验值和导出后重新导入的验证结果。`Content/GHSTwinUI/data/storage-capacity.json` 是运行时对应表，包含 13 个分组的实例数量、全局槽位起点、每实例槽位数，以及货架局部槽位包围盒。提交或归档时应同时保留 FBX、两份元数据和 `lod-policy.json`。

货架 UV0 仍用于原有表面映射。UV1.x 保存局部槽位整数：同一个托盘及其纸箱、胶带和标签使用相同值；钢架使用 `-1`。同一三角形的三个顶点必须具有完全相同的槽位值。导入启用完整精度 UV，保留两个 UV 通道并关闭 Nanite。实例自定义数据的第 0 项保存 `base_slot + instance_index * slots_per_instance`；地堆的局部槽位恒为 0。

货架材料槽顺序保持 `Upright / Beam / Braces / Pallet / Cargo / CargoEdges / Detail`。前 3 个钢架材料原样保留；其余材料从当前场景实际材质图复制到私有目录，仅加入 Masked 不透明度遮罩，保留现有颜色与表面表现。Detail 同时含货架孔位和货物标签，前者的 `-1` 标记使其在货架容量为 0 时仍可见；脚板属于 Braces。

CPU 拾取与材质遮罩使用同一稳定排列：

```text
local_slot = floor(UV1.x + 0.5)
global_slot = floor(instance_base + 0.5) + local_slot
rank = (global_slot * 97 + 17) % total_slots
visible_count = floor(clamp(capacity, 0, 1) * total_slots + 0.5)
visible = local_slot < 0 OR rank < visible_count
```

97 与两种总槽位数均互质，槽位排序不随拖动重新抽样；0% 和 100% 是精确端点。材质在整数运算前对插值结果取整，避免可见性边界附近产生碎面。场景射线拾取先过滤隐藏槽位，再比较最近命中；容量或图层变化后，已隐藏货物的选择状态会清除。

`UGHSStorageCapacityComponent` 初始化时扫描一次已标记的场景组件、写入实例自定义数据，并创建共享 MID。当前资产组合产生货架 4 个、地堆 3 个，共 **7 个 MID**。拖动仅更新发生变化类别的 `StorageCapacity` 标量，不重新扫描 Actor、不增删实例、不重建 HISM。图层开关保留当前容量值，恢复后继续显示同一批槽位。

动态遮罩不能更新烘焙或距离场遮挡，因此导入器在这 13 个存储组件上关闭静态阴影和距离场光照参与，并将 VSM 缓存失效设为 `Always`；原动态投影开关保留。该配置有 GPU 成本，验收应记录实测数据，不能仅凭功能测试推断性能。

4 个 LOD 的屏幕尺寸阈值为 `1 / 0.25 / 0.08 / 0.025`。原始减面比例 `1 / 0.55 / 0.30 / 0.18` 会在 9 个网格的 LOD3 整体删除部分托盘，虽然纸箱和 UV 槽位仍然完整。`lod-policy.json` 将这 9 个 LOD3 提高至 `0.30`，使其几何与已验证的 LOD2 一致；`B_Pass_W36176` 保持 `0.18`。这是几何正确性修复，不能省略。远景 LOD 允许消失的是微小胶带、标签等细节 section；钢架、托盘和货箱核心角色及每个托盘/货箱槽位必须完整。最终原生诊断覆盖 10 个网格的全部 40 个 LOD。

再次生成时，在项目根目录用独立后台 Blender 执行：

```powershell
& 'D:/WinAPP/Blender/blender.exe' --background --factory-startup --python 'D:/UEPro/Test/Scripts/ghs/build_storage_capacity.py'
```

该步骤写本目录中的 FBX/manifest 和运行时 JSON，校验原始源文件未改变，并重新导入每个实际导出的 FBX 验证槽位。它不启动 UE，也不修改关卡。当前已交付的 FBX 可直接用于重新导入，无需先生成。

`lod-policy.json` 按 FBX SHA-256 绑定。重新导出可能改变 FBX 字节；导入器遇到策略校验值不匹配会停止。此时必须检查新源几何并重新执行完整 LOD 原生验证，确认减面策略仍满足全部槽位后再更新策略记录，不能直接删除策略或仅改校验值绕过检查。

导入应由单一 UE 编辑器/执行进程负责。先保存用户编辑，打开 `/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`，退出 PIE，确认没有未保存的地图或资产，再在该编辑器的 Python 环境执行：

```python
import runpy
runpy.run_path('D:/UEPro/Test/Scripts/ghs/apply_storage_capacity.py')['apply']()
```

`apply()` 默认保存私有资产和当前目标关卡。它检查 owner/version、实例数量、材质角色、源材质 SHA-256、完整 LOD0 三角数、各 LOD 核心材质映射及场景前后快照；私有资源位于 `/Game/GHSZcoolSmartFactory/StorageCapacity/`。重复执行复用已有私有材质，重新导入已归属本流程的网格并应用 LOD 策略，不追加 Actor、实例或重复分组标签；这是结果幂等，不是跳过导入的无操作模式。源材质内容变化或目标存在未知资产时会停止供审查。

导入器不会修改地面材质、原始货架库、旧 Occupancy 网格、原始材质或双托盘网格；所有存储实例的顺序、位置、旋转、缩放必须保留，无关场景对象必须与导入前快照一致。编辑 Blueprint 组件属性可能重建组件，因此脚本在每次编辑属性通知后重新取得 HISM，最后才设置网格、材质和自定义数据并逐值回读。脚本中的 `recover_partial`、`resume_components` 仅用于当次已知失败状态的严格恢复，普通生成/导入不要启用。

当前导入脚本以 `D:/UEPro/Test` 为项目路径，Blender 命令使用本机安装路径；迁移到其他机器时应先核对脚本根目录和 manifest 内的 FBX 路径。

改动几何、材质遮罩或 LOD 策略后，至少运行 `GHS.StorageCapacity.*` 原生自动化，检查实际渲染顶点 UV、每个 LOD 的完整托盘/货箱、CPU 拾取和拖动期间实例不变；再使用真实渲染进程检查 0%/默认/100%、图层恢复和阴影。`Saved/SceneControls/capacity-apply.json` 与 `capacity-lod-slots.json` 是诊断证据，性能报告和截图应单独归档，不作为源资产提交。
