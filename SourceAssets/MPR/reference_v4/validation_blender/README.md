# V4 同机位整场检查

当前 `Authoritative_Overview.png` 使用冻结的参考相机、V4 主楼/外场/周边建筑，以及正式真实橡树和车辆模块。它是待视觉评审的模型渲染，文件名不代表用户已经认可达到 1:1。`reference_render_comparison.png` 将权威参考与该渲染放在相同分辨率的左右画布，底部展示相同像素区域的色样；`reference_color_samples.json` 保存中位数/均值。输入图本身没有被编辑。

`../MPR_ReferenceExterior.blend` 保持可编辑：124 个 LOD0 源网格对应 98 个静态分区和 26 个隐藏共享模块，1,294 个可见实例（主楼 727、外场 567），22 张贴图打包。当前树、车实例由 `mpr_reference_catalog.py` 统一生成，Blender 与 UE 使用同一位置、旋转及冠幅缩放规则；未保留 V3 临时树代理。

`composition_manifest.json` 记录每组源文件与标定的 SHA256；`composition_validation.json` 在重新打开保存后的完整 blend 后检查源版本、所有实例变换、共享网格、相机和打包纹理。最新结果与误差以该报告中的输出哈希和字段为准；源文件更新后必须重新组合并重新打开验证，旧报告不能作为新版本证据。这里不包含室内，不会修改内部仓库资产。

当前正式图已包含草地与水面去周期纹理修复，完整 `.blend` 的 SHA-256 为 `cc17a3270d618b708a7b7865ab71794f9a85a6347a552334f74c281d407d70e4`。重新打开校验通过；四组源清单与 `.blend` 哈希匹配，同画布比较的左右图像区域保持输入原像素，色样统计经过独立重算。这些检查证明版本和比较过程一致，不代表外观已达到 1:1。

生成与检查：

```powershell
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/compose_mpr_reference_v4.py -- --render
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/validate_mpr_reference_v4_composition.py
& '<项目可用Python>' Tools/MPRWarehouse/compare_mpr_reference_v4.py
```

渲染优先使用可用 OptiX GPU，模型生成/FBX 导出仍单线程。本地目录可能留有 `Authoritative_Overview_PROXY.png`、`Authoritative_Overview_REVIEW.png` 等迭代图；它们不属于最终提交，不能代替当前正式图。

主楼几何与相机已经可复核，但颜色、树冠表现及其余外观仍需与权威参考逐项比较。数学/源文件验证通过不等于逐像素一致，也不代替 UE 保存重载、材质、远景抗锯齿或运行性能验收。
