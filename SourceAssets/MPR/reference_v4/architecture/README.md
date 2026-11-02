# MPR V4 主楼外壳与屋面

此版按用户指定的七张参考图独立重建外观，使用已冻结的总览相机校准屋顶板区。原 16 段 CAD 外墙轮廓、74 个门洞与内外地坪/屋面高度保持一致，没有生成或修改内部地板、柱、隔墙和设备。

屋面采用更浅白的面层、6.1 m 网格、鲜蓝薄檐。板缝用 0.15 m 的视觉条带保证总览可读，这不是施工缝的实测宽度。38 个采光箱及 4 个 HVAC 适度放大并增高，使蓝色基座和实际灯光投影接近参考；高度、尺寸、分布仍属于效果图读数与视觉估计。

光伏使用冻结相机的屋面投影读取连续板区、白色通道和留白：6,350 个视觉模块合并为 821 条板带。银框、支脚、电池片贴图用于近景，5 个分区另带 LOD1，去除远处银框/支脚的小面，保留组件底板和重复电池片纹理。LOD1 共 9,852 三角面，不能同时作为单独静态物件放置；按 `lod_files` 绑定到对应 SolarBank。

光伏底座保留四侧与底面，移除与电池片仅相距 6 mm 的顶盖；电池片、UV、银框与支脚不变。`solar_cap_validation.json` 记录 1,642 个顶盖四边面已移除，剩余顶盖为 0，其他几何/UV、边界、材质与实例保持一致。UE 的 SolarBank 关闭 Nanite，继续使用显式 LOD。

`mpr_reference_shell.blend` 包含可编辑分区、隐藏模块库、共享实例和打包贴图；源文件中 LOD1 已隐藏，避免与 LOD0 重叠。`reference_shell_manifest.json` 包含 62 个 LOD0 网格、5 个 LOD1 网格、727 个实例；LOD0 共 131,946 三角面，所有交换文件共 141,798 三角面。材质顺序、PBR 参数、贴图路径、边界与 LOD 对应均以 manifest 为准。

`fbx_validation.json` 记录 67 个实际 FBX 回读通过，覆盖边界、三角面、材质顺序、UV、非退化面和 CAD 轮廓/74 个门洞，最大边界差约 0.0000216 m。`preview_reference_camera.png` 是同机位主楼渲染。此处不宣称 UE 导入后的远景抗锯齿、阴影或最终整场视觉已经通过。

生成脚本为 `Tools/MPRWarehouse/build_mpr_reference_shell_v4.py`，私有几何/材质工具为 `mpr_reference_shell_v4_lib.py`，交换验证为 `validate_mpr_reference_shell_v4.py`，同机位预览为 `render_mpr_shell_v4.py`。它们写入独立 V4 目录，不覆盖 V3 源资源。Blender 建模/导出使用单线程；渲染可使用 OptiX。
