# MPR 主楼外壳：参考图第三版

本目录独立重建主楼外壳、屋面及装卸月台。外观依据用户指定的 `D:/CodexTemp/output/imagegen/industrial-saas/multiview` 七张效果图，准确文件名和 SHA256 见 `reference_shell_manifest.json`。CAD 继续约束平面轮廓与门洞；这些效果图不是建筑施工或测绘资料。

保留原 CAD 的 16 段外墙轮廓及 74 个门洞中心、宽度，其中 72 个装卸月台、2 个地面驶入门。内部地板 Z=0、外地坪 Z=-1.2 m、屋面 Z=13.4 m、外墙顶 Z=13.6 m。没有生成内部地板、结构柱、办公隔墙或室内设备。主楼门洞逐个保留为穿墙开口，再放置可分离卷帘模块。

外壳包含白灰预制板、水平与竖向分缝、蓝色底裙及薄檐口、厚黑色软包、金属卷帘和双观察窗、月台调节板、黄色防撞柱、墙灯、顺序编号模块、端部办公玻璃。编号只表示此模型的排列顺序，不是已核实的运营门号。

屋顶光伏根据最新总览重新读出大片连续板区、错落留白及通道，未沿用旧卫星照片的板区。银框和支脚保留为低模几何，电池片细分使用可重复贴图。参考图到 CAD 的四点标定、6,450 个视觉模块、825 条合并板带及其位置均保存在 manifest；数量只用于可视化，不代表电气组件清单或装机容量。41 个采光箱/HVAC 是参考外观的估计布置。

## 文件与使用

- `mpr_reference_shell.blend`：可编辑模型，包含分区建筑、隐藏模块库、共享网格的 CAD 实例和已打包贴图。
- `reference_shell_manifest.json`：63 个 FBX、各文件材质顺序、米制边界、三角面、实例与 PBR 参数。
- `textures/`：程序生成的墙面颗粒、软包织物、花纹钢板和光伏电池片纹理；未将效果图烘焙成建筑贴图。
- `preview_overview.png`、`preview_dock.png`、`preview_roof.png`：Blender 源资产观感检查。
- `fbx_validation.json`：63 个 FBX 回读结果。

坐标是米制 CAD +Y，FBX forward=-Y、up=Z；UE 位置换算 `X=100*x, Y=-100*y, Z=100*z`，偏航角取反一次。重复模块的局部正面是 -Y，门模块原点为墙中心线、内部地板高度；防撞柱和屋顶设备原点为各自底面。`instance_only=true` 的网格仅根据 `instances` 放置，不能再在世界原点创建一个可见副本。

材质使用 14 个 `MPR3_*` 角色，按 manifest 的顺序绑定。albedo 为 sRGB，乘以线性颜色参数；法线为非色彩 OpenGL 约定，在 UE 导入时翻转绿色通道（`ue_flip_green_channel=true`）。`normal_strength` 是近景细节强度，`MPR3_SolarCells` 的 UV 每个视觉组件循环一次。新外壳无需改变原 GHS 材质。

## 生成与验证

在项目根目录以独立 Blender 后台执行，使用单线程：

```powershell
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/build_mpr_reference_shell.py
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/validate_mpr_reference_shell.py
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup -t 1 --python Tools/MPRWarehouse/render_mpr_reference_shell.py
```

当前为 134,552 个独有三角面、726 个实例。窗、门、灯、柱、编号和屋顶设备共享模型；光伏按 6 个区域合并。没有新增逐物件 Tick 或碰撞。验证覆盖实际 FBX 文件的尺寸、面数、材质槽、UV、有限坐标、非退化面及 CAD 轮廓/74 个门洞一致性，最大回读边界差 0.0000216 m。这些属于源资产与交换格式验证，不代表 UE 画面、运行帧率或像素流验收。
