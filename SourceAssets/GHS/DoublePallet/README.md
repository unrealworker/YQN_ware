# 地堆区双蓝色托盘

2026-10-22：每组地堆货物改为两层带货托盘，底部和中间各显示一个蓝色底托。保留原有总高度、占地、材质、7530个实例位置及业务身份。

| 规格 | 总高度（米） | 中间托盘底高（米） | 实例数 |
| --- | ---: | ---: | ---: |
| Low | 1.376031 | 0.688016 | 1904 |
| Mid | 1.976031 | 0.988016 | 3726 |
| High | 2.576031 | 1.288015 | 1900 |

占地均为1.2×1.0米；两个底托各保留原0.17米高度，两段货物压缩以容纳中间底托。保留原箱体分格与蓝色材质。每组仍是一个HISM实例和一个业务对象。

- 可编辑源：`double_pallet_storage.blend`；FBX和尺寸清单在本目录。
- 生成：`Scripts/ghs/build_double_pallet_storage.py`，在独立后台Blender运行。
- UE目标：`/Game/GHSZcoolSmartFactory/DoublePallet/Meshes`。三款使用原模型basename，维持CAD元数据查询键；原共享模型不改动。
- 导入：先运行 `inspect_double_pallet_scene.py` 核对无未保存改动，再运行 `apply_double_pallet_storage.py`。仅替换当前Zcool地图三个地堆HISM的网格引用，保存地图。
- 恢复脚本 `restore_zcool_floor.py` 会保留当前同名网格，不再将外观退回共享单托盘。

验证：三款模型的四个LOD全部检查底部和中部两个蓝色高度段的有效几何及宽深高；UE导入包围盒与原模型误差小于0.01厘米；场景中所有Actor变换、实例顺序、材质覆盖和共享源资产哈希均保留。独立游戏加载已保存地图，检查三组实例并截取近景及强制LOD3截图，未改动保存的地图。

证据：`Review/apply.json`、`Review/runtime.json`；实际游戏截图 `Review/DoublePallet_High.png`。详细中低规格及LOD3截图位于 `Saved/DoublePallet`。
