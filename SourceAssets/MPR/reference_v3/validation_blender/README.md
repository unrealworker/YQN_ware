# 完整外景的 Blender 验证

`../MPR_ReferenceExterior.blend` 将三个独立源库按各自 manifest 组合为一个可编辑外景。仅加载主楼 63 个网格、外场 66 个网格和 11 个道具 LOD0 模块；隐藏原点模块库，不导入道具展示摆台、LOD1/LOD2 或仓库内部。110 个分区和 4,719 个实例保留共享网格关系，24 张纹理打包在文件中。坐标继续为米制 CAD +Y，所有放置由源 manifest 决定。

`composition_manifest.json` 记录三组源 manifest、blend 的 SHA256 和组合数量。`composition_validation.json` 通过重新打开保存后的完整 blend，检查源版本、每个实例的位移/偏航/缩放、共享网格关系、隐藏模块库及打包纹理。最大实例位置浮点误差为约 0.0000305 m。

`site_fbx_validation.json` 对最终 66 个外场 FBX 独立回读，192,023 个三角面与源 manifest 一致，材质顺序和 UV 检查通过，最大边界误差约 0.0000763 m。`geometry_audit.json` 进一步记录长薄屋沿的几何与 UV 面积；它们没有零面积面或零面积 UV，UE 的长条切线警告应结合导入精度与最终渲染另行判断。

渲染图为相同源几何的三个视角：

- `South_Overview.png`：接近最新效果图的南向高俯视，查看主楼、后方邻楼、道路与铁路整体关系。
- `SouthWest_Site.png`：西南侧斜俯视，查看屋顶板区、前院落及场地轮廓。
- `DockYard_Close.png`：月台院落近景，检查地面接缝、导向线、门与车辆关系。

这些截图采用 Blender 的统一日光预览，不代替 UE 材质、灯光、保存重载和运行性能验收。全景中 0.11 m 黄线和 0.028 m 铺装缝可能小于一个像素，需结合近景检查，不应仅凭缩略图判定线条不存在。道具、光伏、外墙细节均为用户指定效果图的视觉重建，未声称测绘或施工精度。

项目根目录执行：

```powershell
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/compose_mpr_reference_scene.py -- --render
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/validate_mpr_reference_composition.py
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/validate_mpr_reference_site.py
```
