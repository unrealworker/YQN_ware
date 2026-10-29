# 双托盘地堆远景模型

状态：**2026-10-29 已通过本地 UE 视觉、性能和原生回归验证，并应用至三个生产 `.uasset`**。服务器及三实例像素流收益需独立验证。

原始 `../double_pallet_storage.blend`、三个原始 FBX 和近景 LOD0/1 保持不变；新源仅替换 Low、Mid、High 三个模型的 LOD2/3。

| 规格 | 实例数 | LOD0（保留） | LOD1（保留） | LOD2 原→候选 | LOD3 原→候选 |
|---|---:|---:|---:|---:|---:|
| Low | 1,904 | 9,600 | 4,800 | 2,112→1,104 | 1,536→864 |
| Mid | 3,726 | 11,640 | 5,820 | 2,560→1,336 | 1,862→928 |
| High | 1,900 | 13,680 | 6,840 | 3,010→1,568 | 2,188→992 |

这些是单个资源的三角数，不能直接解释为 GPU 耗时下降比例。

## 生成

生成器位于 `Scripts/ghs/build_storage_far_lods.py`。使用独立后台 Blender，默认写入本目录，也可指定另外的输出目录：

```powershell
blender --background --factory-startup --python Scripts/ghs/build_storage_far_lods.py
blender --background --factory-startup --python Scripts/ghs/build_storage_far_lods.py -- --output Saved/StorageFarLODReview
```

相对输出路径从项目根目录计算。生成器不启动 UE、不导入资源、不保存地图。`storage_far_lods.blend` 是可编辑远景源；`storage_far_lods.json` 记录尺寸、三角数、三材质槽、双托盘高度、源/FBX SHA256 和本次已应用资产。清单中的 FBX 文件名相对于本目录，原始源路径相对于项目根目录。重新生成会产生新的待验收源状态，不自动延续本次 UE 验收结论。

## 必须保持的约束

- 三款资产路径维持 `/Game/GHSZcoolSmartFactory/DoublePallet/Meshes/SM_GHS_Presentation_Cargo{Low,Mid,High}`。
- 近景 LOD0/1 的顶点、索引、法线、UV 和材质映射不得变化；仅导入 LOD2/3。原屏幕尺寸阈值维持 `[1, 0.35, 0.12, 0.03]`。
- 占地维持 120×100cm；总高度分别为 137.603116、197.603118、257.603073cm（浮点导入允许小于 0.01cm 的误差）。两托盘基座分别位于 0 和原总高的一半，每个托盘保留原 17cm 高度。
- 每件模型仍有两个完整蓝托盘，共 44 个部件；所有底面和真实叉孔保留，不能用封闭蓝方块替代。
- LOD2 去掉远景倒角细分，保留所有独立箱体；LOD3 保留箱垛外面及上下表面、平面格线，并用内缩 5mm 的封闭背衬堵住原 3mm 箱缝后方，避免视线穿透。
- 三材质槽及顺序维持 PalletBlue、CargoBlue、CargoGrid，继续使用项目现有材质。Blender 源的诊断颜色不覆盖 UE 材质。
- 不改 HISM 实例顺序、尺寸、位置、业务身份和 PerInstanceCustomData。地堆容量材质通过每实例编号控制完整地堆显示，其 LocalSlot 为常数 0；不改变该判定，不引入货架 UV1 编号逻辑。
- 不修改地图、货架、设备、碰撞或材质资产；原始源文件必须保持哈希一致。

## 验收

三款模型的 LOD0/1 顶点、索引、法线、UV 哈希完全一致；材质槽、屏阈、原点、包围盒及碰撞精确保留。双托盘、叉孔、格线、外轮廓与阴影检查通过；极近距离强制远景 LOD 时格线比原自动简化版略浅、更均匀，实际近景仍使用未变的 LOD0/1。地堆库容 0/80/100% 分别显示 0/6024/7530 组，0% 无残留货物阴影。13 项原生回归通过，无警告或失败。

同进程对照：RTX 5060 Laptop、独立 Editor-game、1920×1080 原生输入、TSR History150、EarlyZMask1。每档 600 帧，去掉首尾各 10 帧；地堆/追溯为原版→新模型→原版，开顶全景为原版→新模型。

| 视角 | 原版 GPU ms | 新模型 GPU ms | 降幅 |
|---|---:|---:|---:|
| 地堆预设 | 23.414 | 20.197 | 13.7% |
| 追溯 | 20.311 | 17.173 | 15.5% |
| 开顶全景 | 22.675 | 19.647 | 13.4% |

以上为本机渲染测量，不代表 Shipping、浏览器或服务器并发效果。保护范围与测量限制见 `docs/performance/gpu-rendering-20261029.md`。本次只应用三个网格包；地图、容量材质、HISM 实例和其它资源保持原样。原包备份保存在 `Saved/GPUOptimization/StorageLODExperiment/production-backup-20261029-232724`；详细验证与应用结果同目录的 `final-verification.json`、`finalized-import-report.json`、`production-applied.json`。
