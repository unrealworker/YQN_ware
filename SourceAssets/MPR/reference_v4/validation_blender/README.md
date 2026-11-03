# MPR 完整 Blender 外景与来源检查

布局以 `../references/building-road-outline-20261103.png` 和 `../references/all-elements-outline-20261103.png` 为准。`Authoritative_Overview.png` 沿用旧彩色效果图的参考机位，便于对照 `../references/style-focus-20261103.png` 检查材质与整体层次；其名称不代表用户已接受，更不代表新平面与旧透视图能逐像素重合。新图使用独立 X/Y 注册，建筑保持真实正交墙体与共面屋顶，储罐保持真实圆形；不得用剪切网格或拉伸图像伪造匹配。

`../MPR_ReferenceExterior.blend` 是可编辑的完整外景，共享重复构件网格并打包纹理。主仓遵守原 CAD 轮廓与门洞接口，内部资产不进入此组合。建筑、树车与光伏数量从 `composition_manifest.json` 的来源及统计字段读取；道路细修会刷新外场、组合文件与验证报告，因此本文不固定完整场景总数或输出哈希。

`composition_manifest.json` 记录 architecture/site/context/props 各组清单和 `.blend` 的 SHA-256、相机标定来源及组合输出。`composition_validation.json` 重新打开已保存组合文件，检查来源未变、共享网格、实例变换、相机、纹理和输出哈希。源文件变化后必须重新组合和重新打开验证，不能只刷新截图。外场 FBX 的回读证据为 `site_fbx_validation.json`，须匹配当前 site 清单，检查分区数量、材质、UV、三角面与边界。当前外场源为 30 个网格、282,484 三角面；该数字不含重复树车实例的运行绘制成本，也不代表 UE 帧率。

生成与检查入口：

```powershell
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/compose_mpr_reference_v4.py -- --render
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/validate_mpr_reference_v4_composition.py
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/validate_mpr_reference_v4_site.py
```

渲染可使用 OptiX，模型生成和 FBX 导出使用单线程。Blender 与 UE 验证顺序运行。目录内旧 `reference_render_comparison.png`、`reference_color_samples.json`、代理预览或带 REVIEW 后缀的图像是历史诊断，不自动属于最新证据；本文不再引用它们作为当前颜色或视觉验收。

最终布局数据检查见 `../validation/plan_alignment.json`，空间关系见 `../validation/spatial_audit.json`，保存后的建筑几何见 `../validation/context_geometry_validation.json`。实际 UE 视图的归档入口为 `../validation/runtime_views/01…08`、`../validation/plan_views/09…13` 、`../validation/outside_views/14…18` 与 `../validation/detail_views/19…25`，原图哈希和地图版本统一由 `../validation/plan_validation_archive.json` 绑定。`native_visual_review.json` 与 `visual_review.md` 记录人工观察和残差；本轮新材质与源几何完成后仍须刷新原生采集，旧归档不自动代表新画面通过。

光伏以最新实景屋面照片为准，16 个区域中的 18 处封闭孔和全部外沿凹口由近、中、远三级 LOD 共同保持。CPU 源检查入口为 `../validation/pv_source_audit.json`；原生逐姿态审查入口为 `../validation/solar_motion/solar_motion_review.json`。后者使用两版各 96 个相同相机姿态，每姿态停留 0.15 秒，再将实际 PNG 按固定屋顶平面配准。并排 MP4 是采样演示，不是实时录屏；指标降低必须结合蓝面覆盖和空间细节判断，不能把变暗或细节丢失当成无闪烁证明。原图序列保留在 Saved，精选诊断与原图哈希由最终归档绑定。

Blender 来源、顶点或相机校验不等于完美 1:1，也不证明 UE 阴影、抗锯齿、像素流或性能合格。当前运行数据只能来自地图哈希匹配的本轮 UE 报告，不能把旧 2026-11-02 性能或旧截图当成这次结果。
