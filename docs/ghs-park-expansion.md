# GHS 完整园区扩展

目标关卡：`/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`。

用户提供的红线是完整园区的大致边界，也是本次重点展示区域。现有仓库继续作为主体，补齐边界以内的装卸前场、内部车道、停车区、回转区域及出入口；红线以外的公路和住宅仅承担环境定位作用。主视角应能读懂整个园区，而不是只框住厂房。

## 参考与坐标

位置为美国加州 San Bernardino 的 **17335 Glen Helen Pkwy**。参考用户提供的三张卫星图、道路图及红线标注，以及 [Google Maps 对应位置](https://www.google.com/maps/place/17335+Glen+Helen+Pkwy,+San+Bernardino,+CA+92407/@34.1897677,-117.4293908,758m/data=!3m1!1e3!4m6!3m5!1s0x80c34f1ee704ce7b:0x5deb49b79433fae9!8m2!3d34.1894244!4d-117.4287021!16s%2Fg%2F11lj1bmrxg)。道路和停车场按参考形态简化重建；园区边界是展示用估算，不是土地测绘或交通工程设计数据。

现有厂房使用 `SourceAssets/GHS/RefinementV2/Envelope/building_footprint.json` 中的 CAD 轮廓，不旋转、不缩放。坐标约定为 CAD 米转换到 UE 厘米：`UE = (X, -Y, Z) × 100`。厂房长轴约 465.73 米，最大进深约 137.16 米；这两个尺寸用于校准卫星图中的相对比例。

园区布局局部坐标以厂房西北角为原点，`u` 顺厂房长轴向东北，`v` 由背面向装卸前场。转换为 UE 米：`X = u - 239.33385`，`Y = v - 60.24019`。园区原始数据、网格及生成资料集中在 `SourceAssets/GHS/Park`，以最终生成资料为准，不将参考图中的像素位置当作测量值。

| 区域 | 场景方向与布局关系 |
| --- | --- |
| Glen Helen Pkwy | 厂房背面、UE -Y，沿长轴延伸 |
| Sycamore Creek Dr | 厂房西南短边、UE -X，与背面道路相连 |
| I-15 / Ontario Fwy | 装卸前场外侧、UE +Y，斜向经过，采用分离车行带 |
| 园区装卸前场 | 位于厂房与高速之间，西南端较宽、东北端逐渐收窄 |
| 西南端 | 展示停车及出入口空间，并保留货车转向余量 |
| 东北端 | 延续到厂房端部以外，以回转及进出道路收尾 |
| 周边住宅 | 北侧 Gray Pine Pl 一带与高速东南侧，以低模白色体块简化 |

## 视觉和性能约束

沿用当前瓷白、冷灰与深蓝的场景风格。道路采用可辨认的灰度差、浅色路缘与标线；周边建筑简化为白色体块，避免与园区主体争夺注意力。不得把卫星截图直接覆盖为地面贴图。

新增对象使用 `GHSPark_` Actor 前缀与 `GHS_ParkContext` 标签，便于单独重建、筛选与核验。道路等固定几何合并管理；重复建筑、车辆或绿化适合采用实例组。背景对象关闭碰撞和 Actor Tick，不带 `TwinId=` 等现有设备业务标识，不进入仓库设备搜索、选中或状态统计。

保持现有厂房、货架、货物、设备、门牌、材质、实例数量及实例变换。只调整当前关卡 `GHS_WarehouseCamera` 实例的全景中心、距离、俯仰、朝向和平移范围，以容纳完整园区。`MaximumZoom` 为仅类默认值可编辑的属性，保留原有 95,000 厘米上限，不修改共享蓝图或原生类默认值。旧关卡 `/Game/Maps/GHS_CAD_NormalWarehouse` 的文件内容保持不变。

## 可复查证据

`Saved/ParkExpansion/scene_inspection.json` 是改动前的当前关卡基线；`map_before.umap` 是修改前地图备份；`source_map_baseline.json` 保存旧 NormalWarehouse 地图的 SHA-256。不得用扩展后的场景覆盖这份基线。

基线捕获于 2026-10-21 11:21:48 UTC，共 335 个 Actor。随后编辑器在 11:24:34 UTC 记录了用户的 `DELETE` / `ACTOR DELETE` 命令及一个 `TextRenderActor` 的删除，早于 11:40 UTC 的园区导入。与基线核对后唯一缺失项为 `GHS_SiteTitle`，其余原对象一致。因此保留用户对该地面标题的删除，不重新生成。`Saved/ParkExpansion/pre_import_changes.json` 单独记录这一项、基线哈希及日志证据；验证器只豁免这个已确认的导入前删除，仍严格检查其余 334 个原 Actor。

在扩展关卡保存后，通过现有 `Scripts/ghs/live_dispatcher.py` 执行 `validate_park_expansion.py`。验证器只读取场景，并输出 `Saved/ParkExpansion/validation.json`：

- 对照基线及上述独立变更记录，逐一核对 334 个原 Actor 的标签、类别、变换、静态网格、材质、实例数量和实例变换哈希；仅允许全景相机变换改变，相机原有网格、材质、标签仍须一致。
- 检测遗漏或重复 Actor、没有园区归属标记的新 Actor、意外业务标签、碰撞和逐帧 Tick。
- 对照园区 manifest 检查每个网格恰有一个组件及三个辅助拍摄相机；同时检查网格保存材质槽和组件实际材质均绑定到对应角色材质，避免灰白默认材质掩盖绑定错误。
- 重新计算旧地图哈希，确认原关卡未被改写；记录当前保存地图的哈希、扩展 Actor 数量、使用的网格和实例数。
- 失败时写出具体对象与失败原因并抛出错误，不以日志中的普通提示代替通过结果。

另需检查实际 UE 渲染的完整园区视角、装卸前场与入口近景、公共道路和住宅背景，确认边界关系、道路衔接、遮挡与比例。保存后的新进程重载验证和实际运行中的全景／设备聚焦回归属于独立证据，不能由编辑器内的结构检查代替。

此文档描述范围与验收方法。是否通过以最新报告、重载结果和实际截图为准；新增实例数或低模面数本身不能证明 1080P 60 帧或多人像素流性能。

## 2026-10-21 验收结果

当前地图已保存完整园区：12 个环境网格、14,996 个三角面，另有 3 个编辑器拍摄相机。新增 78 个小车泊位、40 个挂车泊位、2 个入口门卫，并用 182 栋住宅白膜、200 棵简化树表现周边。默认全景覆盖完整园区，现有货架和地堆局部视角继续可用。

新进程重载核对通过，334 个原场景对象的变换、材质、网格及实例数据一致。导入前用户已删除的 `GHS_SiteTitle` 单独记录并保持删除；旧 NormalWarehouse 地图哈希不变。UE 无渲染命令行模式不创建编辑器相机图标网格，该差异已与场景模型分别处理。

运行中的 14 项检查通过，包括 1920×1080 与 2560×1600、面板收放、完整园区边界投影、AGV-07 聚焦和详情、全景复位清除选择、货架／地堆视角。实际业务注册数量仍为 106 台设备、56 个设施。截图与验收摘要保存在 `SourceAssets/GHS/Park/Review`。本次未进行多人像素流或稳定帧率基准测试，也未重新生成发布包。

复查运行使用独立 UE 游戏进程，通过 `-ExecCmds` 执行 Python；`-ExecutePythonScript` 在该模式下不会启动此检查：

```powershell
& 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe' 'D:/UEPro/Test/Test.uproject' /Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory -game -RenderOffscreen -TwinDiagnostics -windowed -ForceRes -ResX=1920 -ResY=1080 -unattended '-ExecCmds=py D:/UEPro/Test/Scripts/ghs/verify_park_runtime.py'
```

保留当前工作区 `Saved/ParkExpansion` 下的原始基线与地图备份，用于复查原有对象；不要重新采集并覆盖基线。
