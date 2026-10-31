# 全球仓库入口验收记录

日期：2026-10-31；引擎：UE 5.8.4；本地目标：TestEditor Win64 Development。

## 2026-10-31 精简点位与场景调色

- 删除左下操作提示及减少动效按钮；地球POI改为216×44参考尺寸的单行卡片，移除卡片内城市副标题，侧栏地址和列表城市保留。
- 仓库返回入口统一为“返回运营中心”，原生浏览器槽宽从156调整为200，适配较长文案；返回过渡提示、辅助说明与无障碍名称同步更新。
- 地球自发光倍率0.35→0.15，太阳强度2.5→2.0，天空光0.8→0.6，背景颜色由线性RGB(1.7,3.2,5.0)改为(1.2,2.6,4.2)。保留实际地图灯光朝向、地球纹理、几何与曝光设置，同步离线导入参数。
- `compact-globe/initial.png`、`selected.png`为当前UE与CEF实际渲染截图；`automation.json`记录13项地球测试全部通过；Node策略测试11项、JS语法与目录检查通过，TestEditor编译成功。
- `compact-globe/runtime-result.json`记录Windows 150% DPI可见窗口的两轮入仓/返回成功；极限缩放、复位、自转、相机恢复、HUD重建和仓库卸载均通过。未重新打包或部署服务器。
- 另用原生鼠标在可见窗口选择侧栏仓库、点击进入，确认“← 返回运营中心”在150% DPI下完整显示且不换行，点击后实际返回地球导航。

## 2026-10-31 相机、交互及动效修复

- 缩远消失的根因已经在编辑器回读确认：原双面不透明天空球半径150000cm，小于最大相机臂长200000cm。只修改入口图的背景球至400000cm，并同步导入脚本；不重导地球、不修改仓库图。近端缩放限制为2.5个地球半径，地面平移不会打断球面轨道。
- 自转改为1.5°/秒，交互后暂停2秒、1秒渐进恢复；明确选择“减少动效”时关闭。N和底部重置都恢复初始相机和地球朝向。空白单击取消选择，5px以上拖拽、失焦及捕获取消保留选择。
- 入仓从当前实际姿态出发，2.8秒沿球面转向POI后下降，避免直线穿球；68%–95%进度使用天空色衔接。仓库HUD真实就绪后再开始1.6秒俯冲落镜与界面显现，保留总览构图语义。该方案不是从全球地形连续加载到建筑级地图瓦片，跨尺度交接仍使用短天空色淡变。
- `motion-fix-automation.json`：40项UE测试通过、0失败、0带警告；包括背面、日期线、两极、近表面起点、实际滞后姿态连续性、极限缩放和复位。Node策略测试11项通过，目录及JS语法检查通过。
- `motion-fix-normal` 和 `motion-fix-reduced`：真实UE渲染与CEF各完成两轮入仓、打开屋顶、返回；各40次缩远/40次缩近验证天空覆盖与地表净空。正常模式8秒观察的自转约8.2°，减少动效为0；两模式相机FOV、HUD重建与目的地卸载均通过。保存的截图与JSON为该轮运行证据，不是帧耗时基准。
- 最后的可见窗口（Windows 150% DPI）使用原生鼠标验证选择、拖拽保留、空白取消、滚轮缩放、底部重置、入仓和返回；两次遮罩回执均为1115×627且原生覆盖检查为真。用户后续要求的左上标题移除、右上人形头像/下拉箭头/时钟与日期格式也在该窗口验证。上述离屏截图生成在这两项最后的外观调整之前。
- 保留实际加载门控，超过2秒的真实初始化等待才显示说明。未执行Shipping打包或服务器/Pixel Streaming压测；首次运行仍可能有引擎材质与PSO预热停顿，不把本机测试等同于所有设备的无卡顿保证。

## 设计与资产

- Figma SaasNew 新增“04 · 全球仓库导航”：初始、选中、进入和动效规范四张画板；252节点、151可编辑文本节点、4条原型连接、22个动效节点，缺失字体0。详情见 `figma-acceptance.json`。
- `initial.png` / `selected.png` 是 Figma 导出；`entry-motion.mp4` 为5fps动效相位诊断，不是引擎帧率证明。
- Blender 源文件、真实地理来源、建筑地址交叉核对、FBX轴向校准及实际UE三级LOD报告位于 `SourceAssets/GlobeNavigation`。GHS位置为纬度34.190629582941、经度−117.428430792609，地址级定位，不是测量控制点。

## 自动化与实景

- 编译成功；`ue-automation.json`：32项UE测试成功、失败0、带警告的测试0。覆盖地理、目录、聚合、单目的地流送、常驻相机、DPI遮罩，以及原仓库相机/屋顶/库容。
- `node --test Tools/GlobeNavigation/tests/policy.test.cjs`：7项成功。覆盖2000点预算与成员保留、背面剔除、分页、异常消息恢复、未分区筛选，以及局部更新不重扫目录。
- `node Tools/GlobeNavigation/validate-catalog.cjs`：目录、地图源资产、运行配置与MapsToCook一致。该检查不等于完成Shipping打包。
- `runtime-normal`：普通动效，UE自动化运行的窗口DPI为1，两轮进入仓库、打开屋顶、返回地球；保存四个阶段的引擎截图和状态。150% DPI另由下述可见窗口操作验证。
- `runtime-reduced`：离屏减少动效模式，同样两轮进出；检查自转关闭、镜头恢复、HUD重建、屋顶引用清理与目的地卸载。
- 两种模式的最终结果分别见各目录的 `result.json`。`elapsedSeconds` 包含人为设置的截图和观察等待，不能作为加载耗时或性能基准。

可见窗口还通过原生鼠标操作验证了拖拽旋转、默认视角、POI选择、箭头进入、详情按钮进入、返回和全屏往返。在150% DPI下，窗口的遮罩CSS尺寸为1115×627；全屏为1707×1067，进入和返回回执均匹配，原生完整覆盖检查为真。该手动过程使用Windows原生输入，不是直接调用导航函数。

## 修复的生命周期问题

1. 目标地图放置的Player0相机自动接管，卸载后导致地球黑屏。常驻入口现在拒绝子关卡相机接管，并验证两轮切换始终保留相同Pawn和ViewTarget。
2. 原遮罩用Slate布局单位和CEF CSS像素比较，在150% DPI真实窗口超时。现在与UE的float运算和DPI转换一致，并独立检查实际浏览器覆盖范围；紧凑返回按钮不能授权场景切换。
3. 聚合ID保留前缀、空区域筛选、无效目录消息污染状态和重复目录校验均有对应检查。

## 重跑

先编译TestEditor。自动化命令：

```powershell
& 'D:\UE\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' 'D:\UEPro\Test\Test.uproject' /Engine/Maps/Entry -unattended -nop4 -nosplash -NullRHI '-ExecCmds=Automation RunTests GHS.Globe+GHS.WarehouseCamera+GHS.StorageCapacity+GHS.WarehouseRoof' '-TestExit=Automation Test Queue Empty' '-ReportExportPath=D:\UEPro\Test\Saved\GlobeValidation\AutomationFinal'
```

独立游戏验收参数：`/Game/Maps/GHS_GlobalWarehouse -game -GlobeSmokeTest -windowed -ResX=1672 -ResY=941 -ForceRes -NoSound`。减少动效添加 `-GlobeSmokeReducedMotion`；离屏将 `-windowed` 换成 `-RenderOffscreen`。该专用入口会在完成后退出自己创建的独立进程，不适用于用户编辑器/PIE。输出固定为 `Saved/GlobeValidation`，两种模式应顺序运行并分别保存结果。

## 证据边界

本轮完成本地编辑器/独立游戏验证，未重新打包、上传或部署Pixel Streaming服务。目录2000条测试验证算法和页面预算，不代表2000个地图的实际内容兼容性或多用户并发容量。开发机上的可交互画面不替代目标服务器的帧耗时、显存、编码与网络压测。现有GHS业务仍通过整体适配器接入，尚未把原订单/设备等所有功能拆成独立插件。

旧仓库 `.umap` 未修改；运行时地图构图依据真实地理位置，和参考图/Figma正交预览并非逐像素一致。
