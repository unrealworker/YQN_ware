# MPR 主仓光伏分片修复

仅替换既有 MPR 关卡的五个 SolarBank 静态网格引用，保留 Actor GUID、组件 Transform、阵列布局、59 块原区域和 195 处设备。原始 `rebuild_b50b57/solar` 资产及输入不改写。

## 导入合同

- `manifest.json` 是导入清单；`meshes` 内有五个 LOD0、对应 LOD1/LOD2、旧网格引用、Actor 标签、精确 bounds、材质槽、LOD 屏幕尺寸及 SHA256。
- 新 namespace：`/Game/MPRWarehouse/Hierarchy20261105`。
- 米制 CAD 坐标，经现有 FBX 流程导入为 UE 厘米：`X=100*x,Y=-100*y,Z=100*z`，无需移动 Actor。
- 槽序固定：`MPRH_SolarFrame`、`MPRH_SolarCells`、`MPRH_SolarCellsLight`、`MPRH_SolarCellsShade`。
- 使用新建 Opaque / DefaultLit 简单材质，精确使用 manifest 的线性 BaseColor、Roughness、Metallic、Specular。不要使用旧太阳能材质父级，其粗糙度上限及低对比度贴图会破坏本次效果。
- Nanite 关闭，无碰撞，无自动降面。显式导入三个 LOD；LOD1 与 LOD2 几何相同，以防远处再次退化成连续蓝面。

## 几何

5636 个原模块中心全部保留，模块在原有单元内对称收缩，留出真实空隙。最小模块缝隙 X/Y 为 0.08/0.12m；每四列/三行的分组边界缝隙为 0.32/0.50m。实际过渡缝隙亦包含 0.20/0.31m。各 LOD 保留同一组模块轮廓、薄银灰框及三档轻微变化的深蓝色。

总三角形：LOD0 **80,320**；LOD1 **23,960**；LOD2 **23,960**。远景没有整块背板。安装轨仍位于原区块两侧；新模块顶高 13.660m，框顶 13.654m，底部安装轨 13.414m。

## 验证与预览

- `geometry_validation.json`：15 个 FBX 回读面数、槽序、坐标 bounds、原输入哈希检查。
- `silhouette_validation.json`：实际 FBX 顶面指纹跨 LOD 完全一致，模块中心不变，超出原区块数量为 0。最近设备间距 **1.004794m**，满足既有 0.85m 要求。
- `solar_camera_1100m.png`：CPU 源几何 LOD2 检视，1920×1080、FOV50、俯角52°、距离1100m。
- `solar_camera_572m.png`：同一方向的 LOD0 近景检视。

预览只包含光伏和中性屋顶，不能代替实际 UE 关卡验收或实时帧率测量。

UE 实拍后的最终颜色由 `final_palette.json` 描述：三个 Cell 的原始线性 BaseColor 乘 0.70，框架、粗糙度和几何不变。`source_contract` 在原始几何验证后派生最终材质；`finish_palette(unreal)` 只更新本轮自有资产，重复执行不会再次乘暗。最终 UE 截图和材质读回见上级 `validation`，上述 CPU 预览保持原始源颜色。

重新生成：在 Blender 执行 `Tools/MPRWarehouse/build_mpr_hierarchy_solar.py`，再执行 `Tools/MPRWarehouse/verify_mpr_hierarchy_solar.py`。后者使用 CPU Cycles 渲染诊断图，不修改原场景。
