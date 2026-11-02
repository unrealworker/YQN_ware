# MPR 场景 GHS 资产复用审计

2026-11-02。只读检查现有脚本、源模型清单及 UE 5.8 live editor。当前已加载地图 `/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`，377 Actors、235 个静态网格组件、60 种网格、13997 个放置/实例。该计数不代表运行性能。

## 可直接引用的单体资产

| 用途 | UE 包路径 | 尺寸/注意事项 |
| --- | --- | --- |
| GHS CAD 货架 A/B/C/D1/D2 | `/Game/GHSRefinementV2/Meshes/SM_GHS_V2Rack_A` 等 | 细分纸箱 V2；底面中心原点；X 为宽、Y 为深、Z 高。A 标准宽3.81m，柱架深1.0668m，含托盘外深1.2192m，柱高9.154m。高度是 GHS 专属规格，不自动成为 MPR 事实。|
| GHS 宽3.7138m货架 | `/Game/GHSRefinementV2/Meshes/SM_GHS_V2Rack_A_W37138` | live bounds确认X±185.69cm、Y±60.96cm、Z0..915.4cm。其余宽度见 `SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json`。|
| 地堆 Low/Mid/High | `/Game/GHSZcoolSmartFactory/DoublePallet/Meshes/SM_GHS_Presentation_CargoLow` 等 | XY1.2×1.0m，高1.376031/1.976031/2.576031m，底面中心原点；双托盘及多层箱；用已有LOD。|
| 装卸门 | `/Game/GHSRefinementV2/Meshes/SM_GHS_V2DockDoor` | live bounds：3.04165m宽、.187665m深、4.2m高；底部中心；门宽/高应与MPR开口核对。|
| 输送机 | `/Game/GHSDigitalTwin/Meshes/SM_GHS_Shared_Conveyor` | GHS资产库有，但当前主关卡未放置；长轴Y；live bounds X[-.527429,.527482]、Y[-1.508961,1.517950]、Z[-.020973,1.157747]m，放地面需补+2.1cm。不可当作天工木马整机替代。|
| KUKA低背AGV | `/Game/GHSDigitalTwin/Meshes/SM_GHS_KukaLowProfileAGV` | .954×1.415×.324m；10材质槽；保留实际设备型号，不随意替代MPR设备。|
| 充电器 | `/Game/GHSDigitalTwin/Meshes/SM_GHS_WallCharger` | 1.71178×.247×1.75751m，Z最低.052492m；7槽。|
| 小车外壳 | `/Game/GHSZcoolSmartFactory/CartShell1026/Meshes/SM_CartShell_1026` | 当前GHS使用6个；对照设备资料后再用。|
| 有人叉车 | `/Game/GHSNormalWarehouse/MannedForklift/Meshes/SM_GHN_MannedForklift50k` | 当前GHS使用16台；保留50k优化版。|
| 月台长卡车 | `/Game/GHSNormalWarehouse/TrucksLong/SM_GHN_LongDockTruck` | 当前GHS使用52台；材质在关卡组件覆盖，不能只复制mesh假定颜色一致。|
| 场地闭合卡车 | `/Game/GHSZcoolSmartFactory/Park/Meshes/SM_GHSPark_ClosedTruck` | 当前GHS使用27实例，可按MPR停车资料放置。|
| 社会车辆 | `/Game/GHSZcoolSmartFactory/Traffic/Meshes/SM_GHSTraffic_Sedan`、`SM_GHSTraffic_SUV`、`SM_GHSTraffic_BlueSedan` | 单体可复用；本次不添加GHS交通路径或自动运行系统。|
| 单位墙板 | `/Game/GHSDigitalTwin/Meshes/SM_GHS_WallPanelUnit` | 可复用规则墙段；新的CAD轮廓/屋顶须独立生成。|

## 材质与风格

普通资产材质均可按槽覆盖，不修改共享mesh：

`/Game/GHSZcoolSmartFactory/Materials/M_Zcool_` + `Porcelain / WallTop / PaleGray / Cargo / CargoSeam / Cobalt / SoftBlue / Charcoal / Rubber / Metal / Glass / Cyan / SafetyRed / SafetyAmber / Skin / FloorGrid / SurroundGrid / Sky / Invisible`。

V2货架7槽顺序为 Upright、Beam、Braces、Pallet、Cargo、CargoEdges、Detail。匹配当前白蓝效果的普通材质顺序：`Porcelain,Cobalt,Porcelain,Cobalt,Cargo,CargoSeam,Charcoal`。当前GHS用 Capacity 版本网格和动态容量材质；MPR场景可用普通V2网格加这些普通材质，避免绑定GHS库存元数据。

地堆3槽：Cobalt、Cargo、CargoSeam。

园区基础材质目录：`/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_` + `Ground,Hardstand,Roads,ContextRoads,CampusRoads,Curbs,Markings,Buildings,Roofs,Landscape,Trees,TreesLight,TreesDark,Trunk,Glass,Blue,Detail,Fence,Solar,Rubber,VehicleLights`。

屋顶材质目录：`/Game/GHSZcoolSmartFactory/Roof/Materials/M_GHSRoof_` + `Roof,Seams,Blue,Skylight,Detail`。办公室玻璃 `/Game/GHSZcoolSmartFactory/OfficeFacade/Materials/M_GHSFacade_Glass`（导入前确认asset存在）。

不要直接复用 `VisualPolish/M_VisualPolish_*`：其世界空间掩码/地块边界与GHS坐标绑定；也不要给MPR使用GHS Roof/ScanReveal、RoadTerminalFade的坐标效果。

新近实景风格以 `SourceAssets/GHS/VisualPolish/visual_polish.json` 和 `SourceAssets/GHS/Park/reference_style.json` 为参考；早期 GHS_Normal 的棕箱/深灰地方案不是当前目标。Live灯光读数：方向光强度3.65、光源角9°、旋转(-55,-38,0)；天空光.42，指定GrayLightTextureCube，非实时capture；下半球颜色(.055,.075,.1)。VisualPolish的AO1.1、半径150cm、质量80，bloom .015；曝光EV0锁定，GI/反射NONE。新地图可以复制仅环境设置或逐项配置，不运行GHS修改脚本。

## 必须按MPR重新生成的几何

GHS `SM_GHSPark_*`（除了ClosedTruck）、`SM_GHS_V2Exterior*`、主屋顶、玻璃立面、道路末端等都是整个加州场地或建筑合并网格。复用这些整网格会把GHS轮廓搬入MPR；应仅复用材质、几何生成方法和独立单体。

同款低模圆冠树可复用 `Scripts/ghs/park_vegetation.py` 的无副作用函数 `build_tree(api,u,v,size=1,variant=0,base_z=.025)`，api=`{'mesh': emitter}`，emitter签名 `(role,vertices,faces)`；输出角色Trees/TreesLight/TreesDark/Trunk。3变体高度8.6/10.8/8.7m，半径4.05/3.7/4.6m；在原点导出单棵后按MPR位置HISM实例化。现有LogisticsWarehouse独立树是每棵约5万～6万面且风格不同，不建议优先使用。

## 安全创建及运行隔离

- 独立路径建议 `/Game/Maps/MPR_CAD_Warehouse` 和 `/Game/MPRWarehouse/...`，所有新Actor标签MPR_*，不改GHS地图、基础材质、Blueprint默认对象。
- 可在独立editor进程 `LevelEditorSubsystem.new_level()` 创建空地图，再生成建筑/HISM/灯光/相机并保存指定新包。也可new_level_from_template后严格去除GHS所有建筑/设备/业务Actor，但空图更易保证来源清晰。
- 复用 `Scripts/ghs/ue_instancing.py:spawn_group` 已有 `/Game/GHSDigitalTwin/Blueprints/BP_GHS_InstanceGroup`，批量add_instances(world_space=True,update_navigation=False)。该模块导入无副作用；现有模板存在时不重建。调用后将GHS泛标签替换MPR标签，并重新获取HISM组件以防construction重建；不要改模板。
- UE用厘米；原CAD本地米转换 `(x,-y,z)*100`，CAD yaw取负。FBX -Y forward/Z up，import scale1；用bounds检查方向和尺度。
- 当前 `GHSWarehousePlayerController::BeginPlay` 只有map名包含GHS_CAD_NormalWarehouse才启动HUD/交通。MPR独立命名不会自动显示GHS页面。相机可复用 `/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseCamera` 放置实例并设auto_possess_player PLAYER0，设置MPR overview_center/distance/pitch/yaw/maxpan，再reset_overview；world game mode可用 `/Script/Test.GHSWarehouseGameMode`。
- 该Controller仍默认有Roof/Capacity组件；不要复制`GHS_WarehouseRoof`、`GHS_OfficeFacade`、`ZcoolSequentialDockNumber`、`GHSStorageGroup:*`、`TwinId=GHN_*`等GHS业务标签。Roof有GHS硬编码轮廓，Capacity读取GHS固定data文件，避免MPR误触发。若独立MPR运行需要严格零业务初始化，可用独立基础controller/game mode而保留相机Pawn，不在本轮扩展业务。
- `Scripts/ghs/build_ue_scene.py` 等历史入口受CAD修订保护且会写GHS地图；只读借鉴函数，禁止执行其main。`setup_warehouse_camera.py`也固定GHS目标，不能原样运行。
- 验证新map保存重载、数量/尺寸/材质、俯视和斜视截图、单独运行无GHS HUD/交通；旧GHS内容hash保持。多仓库目录和页面本轮按用户最新要求不开发。
