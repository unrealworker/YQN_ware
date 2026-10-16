# AGV 参考图模型交付说明

模型按用户提供的单张图片重建，已制作 Blender 可编辑源文件并导入 Unreal Engine。采用用户同意的车身名义长度 **1.6 m**，其余尺寸按图片比例估算；包含外部突出零件的实际包围盒约为 **长 1.640 × 宽 0.956 × 高 1.101 m**。隐藏面和不可辨认细节为推测重建，模型不具备工程精确的 1:1 尺寸依据。

| 文件 | 用途 |
| --- | --- |
| [AGV_Reference.blend](D:/UEPro/Test/SourceAssets/AGV_Reference/AGV_Reference.blend) | 可编辑源模型，保留 566 个零件 |
| [SM_AGV_Reference.fbx](D:/UEPro/Test/SourceAssets/AGV_Reference/SM_AGV_Reference.fbx) | UE 导入文件，合并为 1 个静态网格，181,517 个三角面、20 个材质 |
| [AGV_Blender_Preview.png](D:/UEPro/Test/SourceAssets/AGV_Reference/AGV_Blender_Preview.png) | Blender 渲染预览 |
| [AGV_UE_Closeup.png](D:/UEPro/Test/Saved/AGV_UE_Closeup.png) | UE 仓库场景内实际近景 |
| [AGV_UE_Context.png](D:/UEPro/Test/Saved/AGV_UE_Context.png) | AGV 与仓库装卸区整体效果 |
| [reference.png](D:/UEPro/Test/SourceAssets/AGV_Reference/reference.png) | 建模参考图片 |
| [manifest.json](D:/UEPro/Test/SourceAssets/AGV_Reference/manifest.json) | 尺寸、零件、网格和材质清单 |

UE 中可复用的蓝图路径为 `/Game/AGV_Reference/Blueprints/BP_AGV_Reference`，静态网格路径为 `/Game/AGV_Reference/Meshes/SM_AGV_Reference`。打开 `/Game/Maps/LogisticsWarehouse`，在世界大纲中搜索 **AGV_01_Reference**，即可找到已放置的实例，其位置为 **X=-2700、Y=4700、Z=8 cm**。

需要增加车辆时，将 `BP_AGV_Reference` 从内容浏览器拖入场景；需要修改整体大小时，在实例的 Transform 中统一调整 X、Y、Z 三轴缩放。需要调整零件形状时，可编辑 Blender 源文件后重新导出、导入。模型正面朝向本地 **-X**，向上为 **+Z**。

本次交付为静态外观模型；尚未加入车辆运动、车轮转动、导航控制或真实遥测连接。UE 蓝图和实例可以复用，但这些功能需要后续单独实现。

已在独立 UE 进程中重新加载保存后的资产，核验蓝图默认网格、20 个材质槽、实例位置与尺寸均已保留。导入和复核详情见 [AGV_ImportReport.json](D:/UEPro/Test/Saved/AGV_ImportReport.json) 与 [AGV_Verification.json](D:/UEPro/Test/Saved/AGV_Verification.json)。蓝图编译结果为 **0 errors、0 warnings、0 个加载失败的蓝图**，见 [AGV_CompileBlueprints.log](D:/UEPro/Test/Saved/Logs/AGV_CompileBlueprints.log:953)。
