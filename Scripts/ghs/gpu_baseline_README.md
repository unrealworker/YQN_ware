# GPU 基线与画质核验

`gpu_baseline_views.py` 用独立 UE Editor-game 进程采集实际 GPU 时间戳、GPU pass、DrawCalls、相机和后处理状态，并在性能采样后截图。它不保存地图、材质、网格或项目配置；结果写入 `D:/UEPro/Test/Saved/GPUOptimization/<模式>_<UTC>/`。

## 启动约定

- 使用已编译的隔离 `.uproject` 和独立 Binaries。保留用户已开的编辑器，不关闭、不重启、不覆盖其 DLL，也不保存用户未保存的场景改动。
- 隔离 `Config/DefaultGame.ini` 必须先设置 `[StartupActions] bAddPacks=False`，命令行也加下列覆盖。继承 `True` 会在普通编辑器启动时重新导入 StarterContent；即使 Content 使用 junction，也可能写回原工程。
- 同一时刻只运行一个自有 GPU 测量进程；不要同时构建、cook、编译着色器或运行其他 UE 压力测试。记录 PID，只管理自己启动的进程。
- 新配置引发着色器编译时先完成预热再采样；首次黑色占位材质不是可接受的发布画面。正式包须重新 cook 相应着色器。

PowerShell 示例，`$gpuProject` 指向已构建且已禁用 StartupActions 的隔离项目：

```powershell
$gpuProject = 'D:/UEPro/Test/Saved/GPUOptimization/Build20261029-204404/Project/Test.uproject'
$gpuArgs = @(
  $gpuProject,
  '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory',
  '-game', '-RenderOffscreen', '-Windowed', '-ForceRes',
  '-ResX=1920', '-ResY=1080', '-NoSound', '-NoSplash',
  '-unattended', '-NoVSync', '-TwinDiagnostics',
  '-ini:Game:[StartupActions]:bAddPacks=False',
  '-ExecCmds="py D:/UEPro/Test/Scripts/ghs/gpu_baseline_views.py"',
  '-abslog=D:/UEPro/Test/Saved/GPUOptimization/gpu-baseline.log'
)
$gpuProcess = Start-Process 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe' `
  -ArgumentList $gpuArgs -WindowStyle Hidden -PassThru
$gpuProcess | Select-Object Id, StartTime
```

完成后脚本退出该自有进程。若在发现游戏世界之前异常退出脚本，检查日志和记录的 PID；不要按进程名批量结束编辑器。此 Python 脚本不适用于没有 Python 插件的 Shipping 包。

## 模式

一次最多加一个模式参数；不加时使用正常基线。

|参数|核验内容|
|---|---|
|不加参数|闭顶首页、开顶全景、地堆预设、货架预设、追溯，保留当前画质配置|
|`-GPUHistoryProfile`|同进程 History200→150 的 CSV 与 ProfileGPU 分解，随后地堆预设；需要结合启动顺序解释结果|
|`-GPUVisualQA`|History200/150/100 的同机位屋顶、玻璃和步进旋转截图|
|`-GPUDepthQA`|当前配置五机位、地堆/货架0/80/100%近景、玻璃/车/树和屋顶溶解；要求当前History150，用于外部已配置好的mask0/mask1对照|

已拒绝的屋顶遮挡、整体隐藏库存和材质顶点化实验不在此脚本中。EarlyZ等需重启的配置应在隔离工程外部设置，脚本本身不更改或保存这些配置。

可选加 `-GHSStreamControlDir=D:/...`，该本地目录必须预先存在。脚本仅读取属于当前PID的 `metrics.json`，将GPU/GT/RT/RHI、AA及TSR的原生诊断快照附到每个视图；不会写budget。

## 读结果

`report.json` 包含原始/生效cvar、实际PP覆盖、相机、地图前后SHA、逐视图CSV统计和截图路径；`latest.json` 指向最新报告。每视图600帧，去掉首尾各10帧；截图和ProfileGPU在CSV采样之后执行。采样临时请求原生1080p、100%屏幕比例、关闭动态分辨率/VSync与帧率上限，退出时恢复cvar；其他画质维持原配置。

`success=true` 仅说明流程完成，不能证明60FPS或三个客户端流畅。RHI的PrimitivesDrawn包括非三角图元，不是精确可见三角面数。静态截图/步进截图也不能代替连续运动和浏览器端验证。比较时必须控制二进制、分辨率、供电、GPU后台负载与热状态；记录ProfileGPU和真实PP，不能仅用项目cvar推断Lumen是否生效。服务器并发容量仍需服务器GPU与各客户端WebRTC统计。
