# MPR 光伏可见单元放大

针对上一版单元过小、白缝过密，将原 5,636 个网格单元在各自原区块内合并为 **905 个可见单元**。常规合并为 3×2，标准节距 3.36×3.90m，扣除边缝后的实际面约 3.28×3.82m。边缘余数均衡吸收为 3×3 等尺寸，避免新生成一列细条；原来本身只有一格宽的狭窄区块保留原宽度。

- 内部净缝统一 **0.08m**，不再周期性加入 0.32/0.50m 宽缝；薄框宽度从 0.025m 减至 **0.015m**。
- 仅在原 **59 个区块**内部重分网格，区块范围、组间通道、屋顶孔洞及 **195 处设备**保留。
- 原区域内几何覆盖率由 66.32% 升至 **95.68%**，蓝色面覆盖率 94.08%，减少远景白色网格干扰。
- 继续使用上一轮已验收的深蓝最终材质（Cells 为原色线性值 ×0.70）；本轮不新建或修改材质。
- LOD0/1/2 三角形合计 **14,086 / 5,036 / 5,036**。三个 LOD 保持相同可见单元轮廓，最低 LOD 仍有真实间隙。

## 导入

在原关卡 `/Game/Maps/MPR_CAD_Warehouse_B50B57` 中调用 `Tools/MPRWarehouse/mpr_solar_units.py` 的 `preflight(unreal)` 或 `apply(unreal)`。

新网格路径：`/Game/MPRWarehouse/SolarUnits20261106/Meshes/SM_MPRSU_SolarBank_<bank>`，bank 为 `00_0`、`01_0`、`01_1`、`02_0`、`02_1`。来源是当前 `/Game/MPRWarehouse/Hierarchy20261105/Meshes/SM_MPRH_SolarBank_<bank>`。

沿用现有四槽材质，槽序：`MPRH_SolarFrame`、`MPRH_SolarCells`、`MPRH_SolarCellsLight`、`MPRH_SolarCellsShade`。FBX 米制 CAD +Y，UE 为 `X=100*x,Y=-100*y,Z=100*z`。`manifest.json` 列出精确 bounds、15 个 FBX 的 SHA256、三个 LOD 阈值与旧网格映射。

`apply` 只导入并保存五个新网格，再修改原五个 Actor 的 mesh 引用；保留 GUID、Transform、组件属性、已有材质覆盖，不新增 Actor、不保存地图。所有导入资产通过读回检查后才替换引用。目标资产只有来源标记与源哈希精确匹配时才复用。地图保存及全场景保护校验交由主执行器。

## 验证

`geometry_validation.json`：15 个 FBX 回读，bounds 误差小于 0.002m、面数/槽序匹配、所有 LOD 顶面指纹一致。原 5,636 个格位无重叠地完整归入 905 个单元，所有单元位于所属原区块内部。最近设备净距 **0.915028m ≥ 0.85m**。原太阳能来源文件哈希保持不变。

`Tools/MPRWarehouse/test_mpr_solar_units.py` 的 6 项 CPU 测试通过，包括完整覆盖，以及错误关卡、材质、bank 集合、FBX 哈希和越界来源拒绝检查。

`previous_1100m.png` / `larger_units_1100m.png` 与 572m 版本是相同镜头、相同最终材质、相同灯光的 CPU 几何预览，仅包含光伏和中性屋顶。最终效果及运行帧率以 UE 同机位验收为准。

重新生成来源：Blender 后台执行 `Tools/MPRWarehouse/build_mpr_solar_units.py`。预览生成脚本为 `Tools/MPRWarehouse/render_mpr_solar_units.py`。所有新来源均写入本目录，上一版不改写。

## UE 实景验收

已原位应用并保存现有 MPR 关卡。独立 UE 进程重新加载验证通过：只替换原 5 个光伏 Actor 的网格引用，其余 850 个 Actor 保持一致；四槽材质与 3 个 LOD 的三角形数均已读回核对。

`acceptance/` 保存原生 UE 前后截图、场景保护报告与重载报告。截图采用相同相机、FOV 50°、1920×1080 分辨率；修改前截图早于本轮道路修复，因此道路差异对应独立的道路提交，光伏对比使用 `before_02-solar.png` 和 `after_02-solar.png`。最终运行编号为 `20261106T031440451552Z`。

固定总览预热 12 秒后采集 15 秒原生 CSV，共 1,460 帧，平均 **97.31 FPS**，平均帧时 **10.28ms**，P95 **12.16ms**。这是 UE `-game` 离屏静态总览结果，不代表完整业务交互或 Pixel Streaming 性能。验收未保存临时相机，地图文件前后哈希相同；现场编辑器已恢复实时视口且无未保存资产。
