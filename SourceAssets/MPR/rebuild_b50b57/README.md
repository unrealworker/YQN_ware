# MPR B50B57 独立重建场景

新版关卡：`/Game/Maps/MPR_CAD_Warehouse_B50B57`。

以用户提供的 Topoexport B50B57 Blender 基础模型统一重建全场地道路、铁路、建筑、绿化与地形。最新参考图用于环境色彩、材质层次与细节风格。2026-11-05 已按用户授权删除旧关卡及626个旧专属包，144个仍被新版或其他资源引用的共享包保留；清理证据见 `retirement_20261105/`。旧 Blender/FBX/JSON 源文件仍作为迁移来源和可追溯构建输入保留。

当前道路铁路修订见 `transport_revision_20261105/`。下面的首次重建入口和原 `validation/`、`scene_ownership.json` 属于2026-11-04的历史迁移证据，不应再从已退役的旧地图运行。当前地图验证使用 `Tools/MPRWarehouse/validate_mpr_current.py`，独立重载使用 `validate_mpr_current_reload.py`。

主楼外壳、门窗与附属构件、屋顶及全部内部构造从当前场景复制，按对象/组件/实例快照逐项比较。除下述五个光伏网格引用外，主楼网格、变换与内部构造保持不变；用户另行授权在新副本中调整77个外观材质槽位，范围限定为屋顶、白色外墙、工业蓝及三档光伏材质。原材质及其父级和贴图不写入，新版使用独立命名空间中的副本。其余保留槽位仍逐项核对原快照。验证时显式记录来源到副本的 GUID 映射，不假设 GUID 必然变化，也不把标识差异当作几何变化。

光伏重排是另一项明确例外：仅替换原五个 SolarBank 对象的网格引用，新网格为 `SM_MPRR_SolarBank_{00_0,01_0,01_1,02_0,02_1}`。对象变换、材质槽及195处屋顶设备位置保留，原光伏资源不改写。16个主要分区在统一模块网格上整齐成组，贯通设备检修通道，移除细尾和零散小岛；共5,636个模块、59个矩形块，设备实体最小净距约0.875米。分区主要位置与关系保留，边界经过规整，局部覆盖面积会变化，不作为发电容量规划。近、中、远三档 LOD 使用完全相同的顶面占地，避免切换时阵列形状跳变。

## 组织方式

- `inputs/`：原始基础模型、原始坐标提取、主仓配准、许可证、用户效果参考。
- `MPR_B50B57_Rebuild.blend` 与 FBX：独立外围几何；重复树和车辆在 manifest 中记录实例，复用原资源。
- `manifest.json`：网格、材质、实例、高程和新地图导入契约。
- `layout.json`：全源路网、铁路与水域几何，不沿用已取消的外围拼接。
- `geometry_audit.json`：建筑/绿化避让、车辆、铁路、地形基础等检查。
- `solar/`：独立光伏布局、平面对比图、5个网格及其三档 LOD（15个 FBX）、Blend与源验证报告；不改外围主清单。
- `protection_plan.json`：旧关卡主楼保留及外围移除清单。移除仅发生在新副本。
- `scene_ownership.json`：成功导入后记录新关卡及新资源哈希、保留对象映射。
- `validation/`：用于归档最终 Blender、原生 UE 重载、实际画面和性能证据；执行中的报告先写入 `Saved/MPR/rebuild_20261104/`。

地形以主仓地坪为锚点，主仓外50米内保持地坪高度，50至90米平滑接入基础地形；外围30米落到背景平面，保证真实道路末端淡出时不陷入地面。路网内部没有渐变，也不为收边自行闭合开放道路。

建筑按空间分块合批；重复树和车辆使用 HISM。大型背景使用一个网格。道路与铁路共用地形采样，火车是完整连续编组，车辆保留车头和车轮。水面下方地形裁开，并补闭合岸坡。

路面、路缘与标线沿实际地形三角面切分，避免分别插值产生穿插。主仓绿带增加78棵小乔木；两栋邻仓设置39组低矮屋顶设备和独立前场铺装。外围主清单为564个新网格、610,856个三角形；独立光伏清单、复用的主楼和 HISM 模型不计入这个数量。

## 材质与照明契约

`mpr_rebuild_style.py` 将用户给定的 sRGB 色值按 IEC 61966-2-1 转换为线性颜色：背景建筑 `B9BEC5`、混凝土 `B7BAB8`、路面 `7F8891`、草地 `AEBBA3`，树冠以 `94A58B` 为中心作三档轻微变化。主楼屋顶 `DDE3E8`、外墙 `D1D7DB`、工业蓝 `174C78`、光伏 `153A60`。上述外观材质使用非金属参数，保留克制的纹理细节，不新增强噪声。

主楼允许替换的六个角色通过 manifest 的 `retained_material_overrides` 明确登记：`MPR4_RoofMembrane`、`MPR4_FacadeWhite`、`MPR4_IndustrialBlue`、`MPR4_SolarCells`、`MPR4_SolarMid`、`MPR4_SolarFar`。光伏副本使用新父材质 `M_MPRR_SolarSurface`，显式迁移原实例的有效 Albedo/Normal 贴图；以线性亮度归一化保留细节，避免原蓝色贴图再次乘蓝色 Tint 后过暗。光伏粗糙度围绕0.35小幅变化并限制在0.25至0.45；几何引用替换按独立光伏清单验证，不扩大材质或对象修改范围。

新版照明契约为白色方向光3.8 lux、光源角3度、间接强度1；天空光强度1，保留原中性灰立方体贴图。项目启用扩展曝光范围，Histogram 的最小/最大曝光锁定为 EV100 +0.3，曝光补偿0。关闭 Bloom 和 LUT，恢复默认分级与中性的局部曝光参数。新后期启用 Lumen GI 与反射，Lumen Scene Detail为4、场景观察距离200,000厘米、最大追踪距离100,000厘米，使用 UE 类型枚举解析。

新版地图包含 `MPRB_EnvironmentRenderProfile`（C++类 `AEnvironmentRenderProfile`），将 `r.LumenScene.GlobalSDF.ClipmapExtent` 设为5000厘米，使六层距离场的最外半径达到160,000厘米，覆盖主仓航拍机位。该设置由关卡对象管理，不修改全局 ini；最后一个配置对象释放时恢复进入前的值。多个活动配置取最大值，运行中外部控制台修改优先，释放时不覆盖用户的新值。复制或重新导入此关卡前须先编译配套 C++ 源码。

## 重建入口

1. 使用匹配的 UE5.8 编译 `Test.uproject` 的 `TestEditor Win64 Development` 目标，包含 `Source/Test/EnvironmentRenderProfile*` 与相应测试；再在独立编辑器进程运行 `Environment.RenderProfile` 自动化测试。关卡中的渲染配置对象依赖该原生类，不可只复制 uasset 而缺少配套模块。
2. 使用独立 Python 3.13 运行 `Tools/MPRWarehouse/run_mpr_rebuild_geometry.py`。本机入口是 `D:/WinAPP/Blender/5.2/python/bin/python.exe`，依赖 `shapely>=2.1` 和 `numpy` 位于 `Saved/ParkRefinement/python_deps`。该入口调用 builder 的 `--geometry-only` 分支，将几何、实例、材质、输入哈希及审计写入 `Saved/MPR/rebuild_20261104/geometry_payload.json.gz`；此阶段不加载 Blender 原生 API。
3. 在新的 Blender 后台进程中运行 `Tools/MPRWarehouse/export_mpr_rebuild.py`，读取上述纯数据，生成 Blend、FBX 和最终 manifest。几何计算与原生导出使用独立进程；导出阶段不加载 GEOS 或 NumPy，也不重新计算场地几何。
4. 构建独立光伏源，按下文顺序完成几何准备、原生导出、`register_mpr_rebuild_solar.py` 注册及光伏 CPU 验证，确定主 manifest 的最终内容。
5. 注册完成后，使用普通 Python 运行 `Tools/MPRWarehouse/run_mpr_rebuild_blender_validation.py --blender D:/WinAPP/Blender/blender.exe`。它在新的 Blender 进程内分批调用 `verify_mpr_rebuild_blender.py`，每批最多64个 FBX；最终9批报告要求同一最终 manifest 的完整覆盖、稳定哈希及各批原生退出码均通过。
6. 使用普通 Python 依次运行 `Tools/MPRWarehouse/preflight_mpr_rebuild.py` 与 `Tools/MPRWarehouse/validate_mpr_rebuild_surface_clearance.py`，验证最终导入契约及实际导出表面的净空。最终分批回读、预检与表面净空检查均须在光伏注册之后；若之后再次修改主 manifest，须刷新这些绑定哈希的报告。
7. 在旧地图 `/Game/Maps/MPR_CAD_Warehouse` 上启动独立 UE 进程运行 `import_mpr_rebuild.py`；首次导入拒绝覆盖已有新关卡或新资源。
8. 重载验证必须另起 UE 进程并同样从旧地图 `/Game/Maps/MPR_CAD_Warehouse` 启动，再运行 `validate_mpr_rebuild.py`。脚本先记录旧图的距离场 cvar，切入新版验证主楼保留清单、77个授权外观槽位、五个光伏网格引用例外及渲染配置生效，再切回旧图验证 cvar 恢复；不可从新版直接启动此验证。
9. 在新版地图运行 `capture_mpr_rebuild_views.py`、`profile_mpr_rebuild.py`，归档当前版本的原生游戏画面及性能结果。

独立光伏几何、导出与源验证输出位于 `SourceAssets/MPR/rebuild_b50b57/solar/`；注册步骤仅另行绑定主 manifest 的两个字段：

1. 普通 Python 配合 Shapely 运行 `Tools/MPRWarehouse/build_mpr_rebuild_solar.py`，生成布局、纯几何载荷与 SVG 平面稿。可另用具备 Pillow 的 Python 运行 `render_mpr_rebuild_solar_plan.py` 生成 PNG。
2. 普通 Python 运行 `Tools/MPRWarehouse/validate_mpr_rebuild_solar.py`，校验195处设备、检修通道、屋顶范围、三个 LOD 的相同占地及输入哈希。
3. 使用新的 Blender 进程运行 `--background --factory-startup --python-exit-code 1 --python Tools/MPRWarehouse/export_mpr_rebuild_solar.py`。此阶段不加载 GEOS/NumPy，生成独立 Blend、15个 FBX及5个基本网格的 manifest，并执行15个 FBX的原生回读。
4. 普通 Python 运行 `Tools/MPRWarehouse/register_mpr_rebuild_solar.py` 预览绑定；需要写入时加 `--apply`。脚本核验独立 manifest及15个 FBX，仅更新主 manifest 的 `solar_rebuild` 与 `retained_mesh_overrides`，使用固定五个对象标识。已正确绑定时不重写文件；若已有 `scene_ownership.json` 且绑定内容需要改变，则须先归档该次导入，再更新绑定。
5. 普通 Python 运行 `Tools/MPRWarehouse/validate_mpr_rebuild_solar.py --fbx`，独立读取实际 FBX，检查三档 LOD 顶面占地、UV、设备净距、面数和哈希，再执行主流程的最终源验证与 UE验收。

外围564个 FBX 已完成9批原生回读验证，合计610,856个三角形；独立光伏布局已通过 CPU 几何校验及15个 FBX原生回读。渲染配置的三个原生自动化测试覆盖多配置取最大值及恢复、外部修改优先、无效请求及清理。最终关卡验收还必须具备当前版本的导入、重载、实画与性能报告，不能用先前版本的截图替代。

全部已有 Content 文件在导入和重载前后按 SHA256 验证，新地图不得依赖已取消的 ExtensionB50B57 资源。不通过旧外景全量脚本重建新版。

导入器是对本次已审查来源快照的一次迁移，`protection_plan.json`绑定当前工作区旧地图哈希，不能直接用于另一版旧地图。换来源时须重新审查保留计划；交付的新地图本身可独立打开，不依赖被取消的增量资源。再次迭代已验证的新图时，`archive_mpr_rebuild_attempt.py --apply`可将该次新图及其专属资源精确归档，保留旧图不动；默认不带参数仅预览，`--restore`支持恢复。

基础数据的道路面较窄，本版按主次道路扩到3.5/6.5/9米并约束建筑净空，轴线拓扑与端点保持。源道路和铁路交叉只提供同一地形采样高度，无法证明实际桥梁结构，本版按展示性平交处理。配准采用主仓16点相似变换，存在约1.35米RMS源轮廓差异；这是展示场景，不是工程测绘模型，也不宣称与参考图逐像素一致。

性能测试仅覆盖本机 UE5.8、1920×1080、单实例原生视口，不代表 Pixel Streaming 网络延迟或多人服务器容量。

## 首次重建验证（2026-11-04历史记录）

最终地图 SHA256 为 `da4144734d1bac198f88912ac3769788b63516854edefdedf13fc599dbff60fd`。独立导入与重载通过，256个保留对象按77个外观槽位和5个光伏网格引用例外核对，其余保留状态一致；1805个旧Content文件及旧ownership文件未变。新版共603个package文件、906个场景对象。

19个原生游戏视角、独立净空/LOD检查、45项CPU测试及3项关卡渲染配置原生测试通过。本机RTX5060 Laptop、1920×1080短时采样：外景平均10.0442ms、P95 11.0039ms；去顶室内平均13.7027ms、P95 14.7942ms。相机缩放、环绕、重置API实际视点回读通过。详见 `validation/index.json` 与 `validation/visual_review.md`；静态截图不代表连续运动无闪烁，也不代表用户已经验收视觉效果。

## 当前交通修订（2026-11-05）

移除用户标出的 E6F/E9C 两条支线，保留其余28条源轨道轴线。6044个枕木统一为2.25米间距及0.23×2.60×0.13米实体尺寸；统一近远段轨头和腹板，避免在距离主仓300米处突然切换密度。道床按保存的地形三角面重新铺设，移除旧重复道床层，实际导出FBX的94,268个采样点最小净空约0.18米。

C27/CA8连接段恢复6.5米路宽，修顺两个标记路口及边线；保留建筑避让、开放道路端点和源拓扑，不自行闭合四周路网。仅真实场地外缘保留原24米颜色渐变，内部连接不使用渐变。CB1贴保留建筑处仍沿实际建筑保护范围避让。

本次替换89个已有网格，移除28个场景对象，保留用户已经手动移除的另一个道床对象。最终877个Actor，256个主仓及内部保留对象未变。未改材质文件，8个铁路网格增加默认腹板材质槽且组件override保持不变。原失效网格仍可从历史构建追溯，当前关卡不再放置它们。

UE5.8重导会使用网格保存的FBX选项；本次入口限定作用域选择legacy工厂并显式维护保存的设置。89个网格均关闭自动碰撞和多余光照UV生成，已有临时凸包已清除。失败尝试、单网格试验及最终恢复均保留，只有成功报告作为验收；原始备份仅存于Saved，不提交缓存或备份实体。

当前地图SHA256：`5285b73b07f3cd46cfff7a379001eadb7ae1b8e0b7e69d8c6da71c4972639daa`。89个FBX三批原生回读、实际铁路几何复核和独立UE重载通过。最终画面与验收索引见 `transport_revision_20261105/validation/`；首次重建的性能数字不代表本次重新测得的帧率。
