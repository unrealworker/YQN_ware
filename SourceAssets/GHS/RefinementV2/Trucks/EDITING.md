# 独立货车模型

两套场景均已逐车拆开，每个场景有 87 辆普通静态网格放置，可分别选中、移动、复制或删除。

- 大纲目录：`GHS/Vehicles/LoadingTrucks`
- 名称：`GHS_DockTruck_001` 至 `GHS_DockTruck_087`
- 所有车辆共用 `SM_GHS_V2DockTruck` 网格资产；两场景分别保留蓝色、普通风格的材质覆盖。
- 只调整位置或数量时，编辑场景里的车辆即可；修改共享网格本体会影响所有车辆。
- 无蓝图封装、无父级绑定、无编辑器群组。

初次拆分的保存后验证：`Saved/GHS_TruckModelsSplitVerification.json`。
备份位置记录在 `Saved/GHS_TruckModelsSplit.json`；旧 V2 报告保留为历史记录。
后续手动调整后，初次拆分报告中的数量、位置与文件哈希只代表拆分完成时的状态。
