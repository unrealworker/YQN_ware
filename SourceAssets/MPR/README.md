# MPR 仓库三维场景

UE 5.8 独立关卡：`/Game/Maps/MPR_CAD_Warehouse`。

本轮仅场景，未新增网页、业务接口、仓库目录入口或 GHS 交通逻辑。地址由用户给定：1001 W Middlesex Ave, Port Reading, NJ 07064。GHS ZcoolSmartFactory 的原地图及共享资产保持不变。

## 尺寸和数据

- 主平面来自用户 `平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf`，精简结果为 `mpr_cad_layout.json`。
- 主图 DXF 标头标记毫米，实际由 42 英寸货架深度、144/192 英寸横梁及 50 英尺柱距确认其单位为英寸，转换系数 **0.0254 米/单位**。
- 主建筑精确 16 点轮廓，面积 **56,408.1891 平方米**；2,867 个货架模块、164 根结构柱、72 个装卸门、2 个驶入门。
- CADMapper 环境图虽也标记毫米，实际单位为米；经 16 点刚体配准，轮廓残差 RMS **0.5846 米**、最大 **0.8980 米**。不缩放或镜像主仓平面。参见 `environment/alignment.json`。
- Blender 中坐标为 CAD +Y、米；导出 FBX `-Y forward / Z up`；UE 使用 X=100x、Y=-100y、Z=100z，不能重复反转 Y。

净高 12.192 米来自业主 [Prologis 物业资料](https://prologis.getbynder.com/m/30d8742808ae0f7d/original/Prologis-Port-Reading_1001-Middlesex-Avenue.pdf)。屋顶结构厚度、办公室高度、门高度、1.2 米装卸高差、屋面光伏/天窗排布及周边建筑高度是参考图重建的展示尺寸，不能作为工程实测值。货架高度沿用 GHS 9.154 米展示规格，MPR 平面未提供相应立面尺寸。

## 模型和材质

- 144 英寸货架、托盘货箱、装卸门和停驻货车引用 GHS 现有模型；设备及主仓延续 GHS 蓝白银、冷白工业风格，树车继续复用 GHS 生成器。
- 外场修订 2 的道路、背景建筑和铁路使用 MPR 自己拥有的四参数 Default Lit 主材质与 17 个材质实例，通过 `SurfaceTint / Roughness / Metallic / Specular` 控制表面颜色、粗糙度、金属度及高光。它们延续 GHS 风格，但不依赖 GHS 父材质的既有节点参数来实现外场调色，也不改写共享 GHS 材质。
- 另有 10 个 HISM 兼容材质实例继续继承原 GHS 父材质，仅覆盖 UE 5.8 的 `InstancedStaticMeshes` 使用标记。它们与上述 17 个外场材质实例用途不同；共享 GHS 父材质文件保持不变。
- 192 英寸货架单独适配宽框：框架外宽 5.0292 米，纸箱和托盘保留原尺寸，仅改变货物列位置，源文件在 `storage/`。
- 独立 MPR 轮廓、厚墙、门洞、办公室和可拆屋顶在 `architecture/`；所有屋顶 Actor 位于 `MPR/Architecture/RemovableRoof` 文件夹并带 `MPR_Roof` 标签，可在编辑器统一隐藏以查看内部。
- `equipment/` 保留按装配书重建的 96 格口参考机，同时按 CAD 另外适配 64/120/短支机。CAD 列数与装配书版本不同，**模型格数不代表确认的现场业务容量**。参数与假设详见其 README 和 manifests。
- `operations/` 包含输送线、弯头、工作台、封箱机、扫描门、溜槽和地面平台，均从 CAD 位姿放置；空白区域和三视图已排除。
- `environment/` 保留配准后的周边建筑位置与轮廓，按照片重建近场道路、标线、铁路细节、停车和绿化；主仓轮廓由主 CAD 决定。外场修订依据及估计边界见 `EXTERIOR_REVISION_2.md`，照片读数不是测绘精度。

## 性能策略

- 货架、托盘、设备、树、车按 60 米网格分批 HISM，避免每个物件一个 Actor，同时保留空间剔除能力。
- 现有 144 英寸货架/地堆使用 GHS 四级 LOD；新宽货架和天工设备使用三档 LOD。近景保留结构和箱体，远景降低细节。
- 当前环境源清单为 67 个网格、179,690 个独有三角面、95 个累计材质槽；355 棵树和 37 辆汽车共享 3/2 种模型，共 392 个实例。近远环境按区域与材质分批，静态几何无 Tick、无碰撞。这是源资产统计，不是 UE 帧耗时或运行验收结果。
- 相机保留 GHS 的原生交互。仅相机/引擎必需系统更新；不启动库存、播放回放、浏览器或车辆交通系统。
- 三角面/实例统计只是结构证据，实际帧耗时以 UE 验证记录为准，不承诺未测硬件或多用户性能。

## 重建与验证

所有生成脚本在 `Tools/MPRWarehouse/`；CAD 原文件不重复加入 Git，保留原路径及 SHA256 溯源。`mpr_cad_extracted.json` 为本地解析中间文件，不作为最终场景接口。

1. `mpr_cad_inspect.py`、`mpr_cad_extract.py`、`mpr_cad_refine.py` 提取主 CAD；环境脚本完成解析与配准。
2. 用独立后台 Blender 执行建筑、环境、设备、作业区和宽货架生成脚本，保留 `.blend` 与 FBX；原始资料与用户正在使用的 Blender 场景不改写。
3. 用完整 UE 编辑器 `-ExecutePythonScript=.../import_mpr_scene.py` 导入并保存指定 MPR 资源。不要通过跨关卡的 MCP 静态反射调用执行整段导入：UE MCP 的旧 world 指针会在切关卡后失效。
4. `validate_capture_mpr.py` 重载验证 HISM 数量、材质引用、碰撞和业务标签，并生成外景/室内/设备/装卸区实际 UE 截图。
5. `profile_mpr_runtime.py` 在 `UnrealEditor -game -RenderOffscreen -MPRProfile -ForceRes -ResX=1920 -ResY=1080` 中运行；每个视角暖机 15 秒、采样 15 秒，截图在采样窗口之外。该流程使用编辑器游戏模式，不能直接作为打包或像素流性能结论。

自动生成证据位于 `Saved/MPR/`；最终经人工查看的截图和验收摘要另存 `validation/`。`scene_ownership.json` 随场景提交并记录地图及生成资源的 SHA256，重建不依赖 Saved 缓存。任何已保存的手动修改、未归属目标或未知 Actor 都会使重建停止；应先合并到源数据或另存场景，不能通过重新 bootstrap 绕过保护。
