# MPR 货架整列避柱方案

本方案沿用 GHS `prepare_rack_spacing_v2.py` 的整列侧移约束与毫米网格动态规划，只修改原有 HISM 实例的水平位置。没有新建关卡、拆架、缩架、改变货架层数或移动柱子、播种机、输送线。

## 原生依据与结果

- 原关卡：`/Game/Maps/MPR_CAD_Warehouse_B50B57`。
- 原关卡 SHA-256：`1af91bb69aeb9643a14b33dad7239f8d300c8e29318a85b48e84737d0c5ecf23`。
- 原 DXF SHA-256：`c316aafe183162c5bef636885b59cc1000c3eecf50d8be645490b4716c6af863`。
- 2867 个货架实例归入 109 整列，跨不同货架类型和 HISM 组件归组；保留各列内全部相对位置。3 mm 归组容差合并 CAD 本来同列、锚点有微差的 5 个货架。
- 障碍依据为 161 根保留柱、142 根补回的真实截面柱、当前 UE 原生网格边界、20 个墙体网格的 3419 个实心构件及 154 个 CAD 门洞。墙体逐构件检查，保留门窗空洞，不使用整面墙的总包围盒阻断通道。
- 原有 118 处实际柱架结构穿透，另有 8 处贴柱接触需补柱脚净距；126 处柱脚约束全部解决。
- 91 列共 2392 架侧移，其余 475 架原位不动；最大侧移 1.575 m。没有新增柱架、墙架、设备或跨列货架碰撞。
- 南侧 3 个货架与 4 个输送线实例已有包围盒接触；该整列锁定原位，4 对接触原样保留，不在本次避柱中改变设备工作区。详见 `validation.json` 的 `retained_existing_fixed_contacts`。

## 净距规则

柱脚外围保留 GHS 同款 100 mm 间距，并加 0.2 mm 数值余量。原通道不足 2 m 时不再缩窄，原通道超过 2 m 时至少保留 2 m；背靠背间隙不缩减。门口检查实际门洞线段至货架的欧氏距离：保留 `min(原有距离, 2 m)`，使用解析禁入区间，独立 GEOS 验证精确距离。

这些数值是本次数字孪生画面及布局约束，并不是消防、叉车型号或运营通行认证。货架之间原有共享边框、柱脚与货架网格导入时不足 0.01 mm 的浮点接触噪声不会被当作新增穿透。

## 文件

| 文件 | 用途 |
| --- | --- |
| `placement_plan.json` | 2867 个源 CAD handle 到当前 actor GUID、组件名、实例索引、原姿态与目标姿态的完整映射；包含全部约束与输入哈希 |
| `validation.json` | 独立 GEOS 多边形交集、门口距离、整列刚性及数量验证；绑定方案文件 SHA-256 |
| `summary.json` | 各整列位移和原/新通道宽度，便于人工复核 |
| `initial_contacts.json` | 原始柱、柱脚净距、设备接触清单 |
| `evidence/manifest.json` | 6 份原生观测数据的原字节与压缩字节 SHA-256；档案合计约 428 KiB |
| `evidence/*.json.gz` | 原 actor/实例快照、原生网格 bounds/LOD、逐构件墙体、门洞、1976 个原包哈希、14 项播种配置与视口；不含关卡或资产备份 |

`evidence` 收录原本在 `Saved` 的必要输入，因此离线几何审计不依赖临时目录。原 CAD 布局、上一轮货架 handle 映射、补柱截面清单仍引用已提交的 `SourceAssets/MPR` 来源文件，哈希见方案。墙体观测包含源 Blender 库哈希与原生 actor 身份。

## 复现

从仓库根目录使用带 Shapely 的 Python 运行（脚本首先加载 `Scripts/_vendor/cad`）：

```powershell
python Tools/MPRWarehouse/plan_mpr_rack_clearance_20261112.py --archived-inputs
python Tools/MPRWarehouse/validate_mpr_rack_clearance_20261112.py --archived-inputs
```

两步分别使用 GHS SAT/动态规划和独立 GEOS 交集/距离复核。`--audit-only --archived-inputs` 只重建原始接触清单。重规划只写本目录 JSON，不读写 UE 场景。归档版验证已经实际通过。

## 原关卡应用与重新加载验证

`Tools/MPRWarehouse/apply_mpr_rack_clearance_20261112.py` 在普通 Python 下支持 `--offline-check`。在原生编辑器中执行 `apply(unreal)`，要求原关卡未脏、当前地图与 1976 个包哈希匹配、924 个 actor 全字段吻合、14 项播种机配置及视口保持原值。只调用现有 HISM 的 `update_instance_transform`，复制原 Transform 后替换 `translation`，保持索引、旋转、缩放、高度、材质覆盖、网格、LOD/culling 和自定义实例数据。

应用前后使用完整 actor/辅助对象/world settings 对照，仅允许这 2392 个实例的平移。验证通过后只保存原地图。输出位于 `Saved/MPR/optimization_20261112/rack_clearance`；已有检查点不能覆盖，也不会自动重新加载或回退场景。

独立 UE Python commandlet 执行同一脚本，并带 `-MPRRackClearanceVerify`，会重新加载原地图并验证完整白名单及所有原包。该入口不写 Content，仅保存验证 JSON。只归一化已在 UE 源码中确认的编辑器临时相机图标、灯光图标尺度和 Chaos 调试辅助对象；不会忽略真实相机、材质、设备或 actor 差异。

原生应用和重新加载结果以对应 `validation.json`、`reload_validation.json` 为准。后续人物显示或性能修改应单独验收，不扩宽本脚本的货架平移白名单。

## 原生验收

已在原关卡保存并独立重新加载验证，结果见 `native_apply_validation.json` 与 `native_reload_validation.json`。924 个 actor、2867 个货架实例及其索引保留，仅 2392 个实例的水平位置改变；其余 1975 个原有 Content 包逐字节保持原样，14 项播种机配置及镜头设置不变。保存后地图 SHA-256 为 `67cec0faee74dd8f38e7c74c4b305aa9bd2dc0c7558efc1ed131bc4ad034a659`。

`validation_views/before.png` 与 `after.png` 是同一原生运行镜头的 1920×1080 截图，曝光、光影、材质、渲染分辨率一致。空间检查覆盖全部 109 列及 303 个柱位，截图用于展示其中一部分。
