# MPR 主仓外围场地

在现有 `/Game/Maps/MPR_CAD_Warehouse_B50B57` 原位实施；所有提交位于 master。

场地新增连续混凝土作业面、725㎡沥青停车面、步行带、转角绿地边界、25段路缘、19个止轮器和195个标线特征。西侧18个、东侧1个小车位及原有挂车位置保留。作业面前的39棵园区补植树移入安全绿带，全部1282棵树使用饱满灰绿树冠；原始树的位置保留。

新增场地按7种材质合并成7个Actor，树木保留HISM实例化及4级距离LOD。原屋顶、光伏、月台、室内及主路总图保留。原有29个对应场地组件隐藏，源资产未覆盖。交通净空为场景几何检查，未进行半挂车扫掠轨迹工程认证。

## 文件和复现

- `site_plan.json`：CAD米制几何方案、源数据SHA、净空审计与39棵树的原位/目标位。
- `geometry/`：7种场地FBX及可编辑Blender源文件。
- `tree/`：树冠FBX、Blender源文件、四材质槽与回读审计。
- `validation/`：两轮同机位原生UE截图、帧时间CSV、资产及对象保留检查。

在工程根目录运行本机Blender Python的 `-m unittest discover -s Tools/MPRWarehouse -p test_mpr_site_completion_geometry.py -v` 验证方案；脚本使用工程现有Saved/ParkRefinement/python_deps中的Shapely。几何源可用 `blender.exe -b -t 4 --python Tools/MPRWarehouse/build_mpr_site_completion.py` 重建。

第一轮脚本仅接受当前打开、未处于PIE且没有未保存地图改动的B50B57。第二轮通过 `apply_mpr_site_round2.run(unreal, apply=False)` 预检，`apply=True` 才修改当前地图；已属于本任务的资产若源FBX更改，需要显式 `refresh_owned=True`，其他资产拒绝覆盖。验证器 `verify_mpr_site_completion.run(unreal)` 读取当前世界，不加载/保存地图；阶段来自Saved/MPR/site_completion_20261105/run_config.json。

截图驱动只在独立 `-own -game -RenderOffscreen -MPRProfile` 进程运行，1920×1080、100%屏幕比例。原地图备份存于Saved；没有新增地图资产。
