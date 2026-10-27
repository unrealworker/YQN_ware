# 小车外壳 1026 · GHS 蓝色展示模型

基于 `D:\DDDownload\小车外壳（1026）.STEP` 的真实装配位置制作，适用于仓库场景实时展示。

当前外观优先版本位于 [`20k/`](20k/README.md)，共 **19,965 个三角面**。该版本恢复原始孔壁、周边圆角和开孔可见的内部结构，后续使用此版本。本目录中的 9,934 面文件保留为上一版。

- 总计 **9,934 个三角面**，包含外壳、驱动轮、万向轮及可见机械零件；摄影棚不计入且不导出。
- CAD 整机尺寸 **382 × 500 × 195.5 mm**，Blender 单位为米，Z 向上，原点位于底部中心。
- 保留上下壳接缝、轮罩、53 处顶板开口及前部大开口的 **20 mm 下翻内壁**。
- 外壳使用项目工业蓝/深蓝，轮胎深灰、五金银灰；颜色写入 Principled BSDF，无外部贴图依赖。
- 隐藏的内部细节、亚毫米工艺圆角与紧固件做展示级简化；不作为机械加工模型使用。

## 文件

| 文件 | 用途 |
|---|---|
| `CartShell_1026.blend` | 可编辑 Blender 源文件，资产和摄影棚分集合 |
| `SM_CartShell_1026.fbx` | 仅导出模型，可供 Unreal 后续导入 |
| `CartShell_1026.glb` | 自带材质的通用模型 |
| `preview_front.png` / `preview_rear.png` | 两侧实际渲染预览 |
| `manifest.json` | CAD 来源哈希、零件面数、材质和坐标说明 |
| `verification.json` | 源文件重开、FBX 回导与 GLB 数据验证结果 |

## 重建

工具：Blender 5.2.2，Python 3.11，`cadquery-ocp==7.7.2`、`numpy==2.4.6`、`pymeshlab==2025.7.post1`。本地 Python 依赖安装于 `Saved/StepTools`，不提交到仓库。

按顺序运行：

1. Python：`Scripts/assets/extract_cart_shell_step.py`，读取 CAD 装配和曲面。
2. Python：`Scripts/assets/retopologize_cart_shell_1026.py`，保留外表面与顶板孔槽，重建简化边缘。
3. Blender 后台：`Scripts/assets/build_cart_shell_1026.py`，配色、制作展示模型、导出和渲染。
4. Blender 后台：`Scripts/assets/verify_cart_shell_1026.py`，重新打开并验证文件。

中间文件全部写入 `Saved/CartShell1026`。Blender 脚本使用 `--background --factory-startup --python-exit-code 1 --python <脚本路径>` 运行。

本交付是独立模型资产，没有替换 UE 场景中的设备。
