# MPR 权威总览相机标定

基准是用户指定的 `ChatGPT 图像 2026年11月2日 15_56_24.png`，尺寸 **1728×910**。CAD 主楼轮廓作为尺度锚点，屋面 Z=13.4 m、外地坪 Z=-1.2 m；周边建筑与环境不再受旧 CAD 外围轮廓约束。

读取主楼 **16 个屋顶角点**和 **4 个可见墙基点**，拟合等像素尺度的透视相机。屋顶误差 RMS **2.013 px**、最大 **3.424 px**；全体 20 点 RMS **2.246 px**、最大 **4.285 px**。单独无限制屋顶单应矩阵 RMS 为 1.982 px，因此相机模型已接近这批手工像素测点可支持的最佳平面匹配。效果图不是严格摄影数据，不能把残差或测点精度宣称为测绘精度。

`camera_calibration.json` 已冻结，包含对应点、K 矩阵、world→CV 相机旋转、Blender 相机 world matrix/焦距/shift、地面和屋面映射。主点落在约 `[725.014,-19.040] px`，因此需要显著纵向偏移 `shift_y=-0.274329`；这代表偏轴裁切的拟合相机，不能删除 shift 后仅保留位置/角度。它也是单图、近似共面数据存在焦距/机位歧义的表现。

Blender 相机参数：位置 `[-15.30369,-812.99572,830.70609] m`，XYZ 欧拉角约 `[58.24539,0.12484,-0.29705]°`，36 mm 横向传感器，焦距 38.62185 mm，shift_x=0.080432。建议直接使用 JSON 的 `matrix_world`，避免欧拉角和坐标约定错误。

`blender_camera_validation.json` 使用 Blender 的 `world_to_camera_view` 独立核对全部点，和解析投影的最大差为 **0.0003401 px**。80 个图像点/高度组合的正反映射误差小于 `1.6e-12 px`，验证的是数学实现一致性，而不是效果图真实精度。

## 映射接口

从 `Tools/MPRWarehouse/calibrate_mpr_reference_camera.py` 导入：

```python
project_world_to_image([x, y, z])  # 返回 [u, v]，图像左上为原点
image_to_ground(u, v, z=-1.2)    # 返回米制 CAD [x, y, z]
```

`image_to_ground` 可接受任何水平 Z 平面。若描的是建筑屋顶边界，应传 `z=-1.2+estimated_height_m`；若描的是路面/地坪则传 `-1.2`。把屋顶像素直接投到地面会造成建筑 footprint 的错误位移。保持 CAD +Y，不在 Blender 中做 UE 的 Y 轴反射。

## 诊断与同机位渲染

- `camera_corner_diagnostic.png`：原参考图上叠加测量点（黄）、拟合轮廓（青）、残差（洋红）。只用于科学诊断，未生成或改造参考内容。
- `camera_roof_diagnostic_close.png`：同一诊断的屋顶放大图。
- `calibrated_main_shell.png`：使用实际 Blender 相机渲染的主楼，周围透明。
- `MPR_CalibratedShell.blend`：主楼与该相机的可编辑检查文件。

这些结果标定机位和几何比例，不代表外观细节、材质、周边环境或 UE 最终画面已达到逐像素一致。生成脚本不会修改现有外场资产或 UE 关卡。
