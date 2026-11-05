# MPR 原关卡分轮验收

目标关卡始终为 `/Game/Maps/MPR_CAD_Warehouse_B50B57`，没有创建新关卡或分支。

## 第一轮：镜头、曝光、光影与颜色

- 三个固定机位：总览、南侧月台与停车、北侧与西侧场地；全部1920×1080、水平FOV50°。
- 仅调整太阳光、固定曝光和组件材质覆盖。877个现有Actor保持；屋顶、室内、月台、车辆及树木几何未改动；746个原MPR共享资产哈希不变。
- 应用前通过当前编辑器桥接核对：进程14400，目标B50B57，`DIRTY_MAPS []`，877个Actor。没有重载编辑器关卡。
- 实际截图：[总览](round1/01-overview.png)、[南侧细节](round1/02-docks-parking.png)、[北西侧细节](round1/03-north-west.png)。
- 15秒原生CSV，1303帧；平均86.86 FPS，平均帧时间11.51ms，P95为13.14ms；GPU时间验证通过。
- 测试环境：RTX5060 Laptop GPU、UE5.8.4、独立`-game -RenderOffscreen -MPRProfile`、100%屏幕比例、关闭垂直同步与帧率上限。编辑器视口实时刷新暂停；非打包/Pixel Streaming/完整业务交互负载验收。
- 初始baseline采样时后台视口状态不同，不将baseline帧率与本轮解释为性能增减。

原始CSV压缩存档、实际相机读回、地图SHA与资产校验见各轮report/apply文件。原地图备份仅保存在Saved，不作为新增关卡。
