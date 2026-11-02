# MPR 周边建筑外观修订

生成入口：`Tools/MPRWarehouse/mpr_context_buildings.py` 中的 `build_context_buildings(api, source, ground_z)`。模块只通过主环境生成器传入的 `mesh/poly/box/strip/zone` 发出几何，不读写文件，不调用 Blender 或 UE。`api` 可为字典或对象，`box` 的 yaw 使用弧度。

实景依据为用户目录中的 `Snipaste_2026-10-30_16-13-26.png`，辅以 `16-02-59` 和 `16-04-43` 图片。照片显示主仓北侧邻仓的深色大屋面、浅色连续仓库立面及朝向主仓的装卸侧；西侧住宅为小体量坡屋顶。原始文件路径与校验值已保存在上级 `source_provenance.json`。

140 栋背景建筑的位置和外轮廓来自 `environment_local.json`，没有挪动或替换为规则街区；主仓1583明确排除。1582邻仓沿用原有14米展示高度，用灰蓝屋顶降低纯白大体块的视觉重量，只增加12条屋面细缝、4处小机组、低矮屋边、连续立面分缝及26处装卸门剪影。26处是压缩的背景视觉节奏，不代表实测月台数量。其它大型建筑细节更少，住宅坡顶使用原屋面三角片沿屋脊分割，投影始终留在原建筑轮廓内。

本模块只使用4个线性颜色角色，建议通过MPR独立材质实例继承GHS材质后覆盖SurfaceTint，不修改共享GHS材质：

| 角色 | 线性RGB | 粗糙度 |
| --- | --- | --- |
| ContextRoof | 0.24, 0.31, 0.37 | 0.82 |
| ContextWall | 0.60, 0.66, 0.69 | 0.82 |
| ContextTrim | 0.39, 0.46, 0.50 | 0.85 |
| ContextGlass | 0.16, 0.23, 0.30 | 0.50 |

返回 `footprints` 为原始XY轮廓，供树木/景观排除；`counts`、`buildings` 提供合并统计和单栋来源；`material_roles` 为上述4个角色。按主环境 `zone` 合并为5个区域网格，全部背景建筑共5357三角形。小型住宅/附属建筑132栋、工业体量8栋，其中116栋采用坡顶；不引入逐栋Actor、动画或碰撞。

独立后台Blender运行 `review_mpr_context_buildings.py` 已验证：140个建筑轮廓点集合与源数据完全一致、主仓未重复、所有屋顶投影面积等于原轮廓、每批不超过4材质槽、顶点为有限数、源JSON未改变。屋顶面积最大差0.001462平方米，来自源文件面积舍入/Blender浮点三角化。详细结果见 `context_buildings_review.json`。

`context_buildings_preview.png` 已目视检查，为仅含背景建筑的隔离预览，故道路、绿化与主仓有意留空；它不代替完整UE场景验收。建筑高度、屋面设备、立面细分和坡度仍是照片推定的展示尺寸，不是工程测绘。
