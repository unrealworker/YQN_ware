# GHS 浅色智慧仓库场景

独立新关卡：`/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`。

在 Unreal 编辑器的 Content Browser 中进入 `Content/Maps`，打开 `GHS_CAD_NormalWarehouse_ZcoolSmartFactory`，点击 Play 即可体验。项目原有默认启动地图未改变。

视觉参考：[阿兰是Alan · 智慧工厂-生产管理数字化 SaaS 系统解决方案](https://www.zcool.com.cn/work/ZNjY0NDI3ODA=.html)。将参考中的瓷白建筑、冷灰细网格、蓝色强调与柔和阴影应用到现有 CAD 仓库。新材质和蓝/青动态效果独立存放于 `Content/GHSZcoolSmartFactory`。

按用户要求，本次不制作新管理面板、顶部导航或侧栏。沿用原有设备标签、分组列表、详情交互和演示数据。

## 操作

- 鼠标左键拖动：围绕地面观察点旋转。
- 鼠标右键拖动：抓住地面平移。
- 滚轮：缩放；Home：回到新场景全景。
- 点击远景设备分组：展开列表，每页 5 项，可翻页选择。
- 点击近景设备标签：查看已有详情，点击关闭按钮收起。

保留装卸车辆 52 辆、人工叉车 16 辆、堆高车 6 辆、AGV 32 辆及充电设施；共 248 个已保存 Actor、13,762 个实例。新图为原图重复的堆高车标识分配了独立编号，原图不受影响。已有演示数据与时间驱动的 AGV 地面效果保持可用；本次没有新增外部数据接入或自主调度逻辑。

## 独立启动

```powershell
& 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe' `
  'D:/UEPro/Test/Test.uproject' `
  '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory' -game -windowed
```

## 验证与复现

- `Scripts/ghs/build_zcool_smart_factory.py`：从当前已保存原场景克隆，创建独立材质，保存并重载核验。
- `Scripts/ghs/verify_zcool_smart_factory.py`：真实游戏运行时设备注册、分组分页、详情、相机及地图完整性验证，输出 `Saved/GHS_Zcool_Runtime.json`。
- `Scripts/ghs/capture_zcool_smart_factory.py`：通过真实 UE 渲染保存四个场景视角，输出 `Saved/GHS_ZcoolCapture.json`。
- `Scripts/ghs/open_zcool_smart_factory.py`：核验原文件哈希并打开新场景，不保存地图，输出 `Saved/GHS_Zcool_FinalEditor.json`。

本次 UE 5.4 Editor 构建通过；GHS 自动化 55 项通过，运行时专项 10 项通过，`WarehouseRuntime.MapDrag` 在新关卡通过（覆盖 20 组相机角度）。构建报告 `Saved/GHS_ZcoolBuild.json` 记录了实例、挂接和设备变换一致性，及 787 个原始 Content 文件哈希未改变。

运行时预览：`Saved/GHS_Zcool_Overview.png`；内部细节：`Saved/GHS_Zcool_ForkliftDetail.png`、`Saved/GHS_Zcool_StackerDetail.png`。

无界面元素的场景截图：`Saved/GHS_Zcool_Scene_Overview.png`、`Saved/GHS_Zcool_Scene_FloorStorage.png`、`Saved/GHS_Zcool_Scene_RackAisles.png`、`Saved/GHS_Zcool_Scene_AGV_Charger.png`。四个视角均经实际渲染及人工查看，截图过程未修改保存的关卡。
