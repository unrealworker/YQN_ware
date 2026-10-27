# 小车外壳 1026 · 外观优先版

来源：`D:\DDDownload\小车外壳（1026）.STEP`。总计 **19,965 个三角面**，46 个非空网格零件，真实装配尺寸 **382 × 500 × 195.5 mm**。单位为米、Z 向上，原点位于整机底部中心。

## 保留原则

外壳轮廓、顶板孔槽、上下壳接缝、R2 周边圆角、深螺钉孔、轮罩和驱动轮轮缘使用原 CAD 表面。大开口的 20 mm 下翻内壁，以及透过开孔可见的电机壳、支架和内侧挡面一并保留。封闭内部和遮挡部分做裁剪与减面，紧固件、底部万向轮采用较低密度网格。

材质沿用项目工业蓝：上壳蓝色、下壳深蓝色、银灰五金与深灰橡胶。颜色写入 Principled BSDF，不依赖外部贴图。模型保留 CAD 的原始造型和真实大小，不按旧设备体积放大。

## 交付文件

| 文件 | 用途 |
|---|---|
| `CartShell_1026.blend` | 可编辑源文件；模型和摄影棚独立集合 |
| `SM_CartShell_1026.fbx` | 模型专用 FBX，供 Unreal 导入 |
| `CartShell_1026.glb` | 带材质的通用模型 |
| `preview_front.png`、`preview_rear.png` | 两侧渲染预览 |
| `manifest.json` | 来源哈希、尺寸、分零件面数和材质 |
| `verification.json` | 文件重开、FBX 回导、GLB 和 CAD 对照检查 |

验证结果：Blender、FBX、GLB 均为 19,965 三角面；FBX 回导尺寸一致；原 STEP 哈希不变。受保护 CAD 表面采样最大距离为 0.0154 mm，33 个顶板通孔与提手槽通过无遮挡射线检查。此数值是受保护网格对输入 CAD 三角网格的检查结果，不代表全部简化内部结构的加工公差。

## 重建

依赖：Blender 5.2.2 LTS、Python 3.11、`cadquery-ocp==7.7.2`、`numpy==2.4.6`、`pymeshlab==2025.7.post1`。Python 依赖位于项目忽略目录 `Saved/StepTools`。

1. Python 执行 `Scripts/assets/extract_cart_shell_step.py`，提取 CAD 装配和曲面。
2. Blender 后台执行 `Scripts/assets/prepare_cart_shell_20k.py`，计算外部及开孔可见性。
3. Python 执行 `Scripts/assets/optimize_cart_shell_20k.py`，分离保护表面，只减面其余部分。
4. Blender 后台执行 `Scripts/assets/build_cart_shell_1026.py -- --20k`，建材质、导出和渲染。
5. Blender 后台执行 `Scripts/assets/verify_cart_shell_1026.py -- --20k`，验证交付文件。

Blender 命令通用参数：`--background --factory-startup --python-exit-code 1 --python <脚本>`。中间文件写入 `Saved/CartShell1026`，不随资产提交。
