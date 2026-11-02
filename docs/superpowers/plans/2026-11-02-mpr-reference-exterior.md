# MPR 效果图外景重建实施计划

> **For agentic workers:** Use subagent-driven-development to implement the independent asset tasks below; keep all UE map mutations on the main worker.

**Goal:** 按用户指定 multiview 效果图，在 Blender 重做 MPR 主楼外壳及全部外景，导入 UE 并原样保留主楼内部。

**Architecture:** 外壳、公共环境、可实例化道具使用独立 Blender 源文件和版本化资产清单。专用 UE 导入流程只替换明确归属的旧外景 Actor，先后对内部 Actor GUID、组件、材质及每个实例变换做一致性检查；重复构件使用分区 HISM 与 LOD。

**Tech Stack:** Blender 5.2 Python、Shapely、UE 5.8 Editor Python、FBX、现有 GHS 相机与内部资产。

**Spec:** 用户 2026-11-02 指令；`D:/CodexTemp/output/imagegen/industrial-saas/multiview` 的六张分视图与最新总览。主楼外形接口由 `SourceAssets/MPR/mpr_cad_layout.json` 约束。

## Global Constraints

- 保留内部地板、隔间、玻璃、立柱、货架、货物、输送线与天工设备的现有 Actor 和资产。
- 新外壳保持 CAD 16 段轮廓及 74 个门洞接口；用户最新确认：外部完全按效果图还原，外围 CAD 不再作为道路、建筑和绿化布局约束。
- 以最新总览图建立固定标定机位，按参考像素反投影重建场地；六张分视图补充细节。V3 视觉效果已被用户否定，不能用其结构验证代替 V4 视觉验收。
- 新外景使用白灰墙板、蓝色底裙和檐边、完整月台、低饱和绿化、灰色道路、混凝土场坪与彩色半挂车；未覆盖区域延续该风格。
- 不开发 MPR 页面，不修改共享 GHS 资产，不覆盖未知用户 Actor，不混入项目文件或解决方案的既有修改。
- 验证后自动中文 Git 提交；源 Blender、FBX、清单与验证证据随实现提交。

## Review Focus

- 外景替换误删室内：导入前后及重新加载后比较内部快照与依赖文件哈希。
- 新外壳门洞与室内错位：检查 CAD 门中心、数量、方向及近景截图。
- 树木压道路、车辆穿墙：按树冠/车辆占地与道路、建筑、铁路做空间检测。
- 视距/LOD导致内容消失或材质回退：重新加载检查 LOD、材质实例权限及远近截图。
- 精细外景拖慢运行：独立游戏固定机位采样外景和内部 CPU/GPU 帧时；保留测试条件。

### Task 1: 主楼与实例模块

**Files:** `Tools/MPRWarehouse/build_mpr_reference_shell_v4.py`, `build_mpr_reference_v4_props.py`, `refine_mpr_oak_canopy.py`; `SourceAssets/MPR/reference_v4/architecture`, `props`。

- [x] Blender 制作外墙、屋顶、太阳能、月台与灯具；输出 CAD 接口审计。
- [x] 制作细叶树木、三色半挂车、轿车及白灰铁路厢车；光伏与周边建筑使用显式 LOD，树木使用 Nanite `PRESERVE_AREA`、`max_edge_length_factor=0` 及共享实例；SolarBank 使用无顶盖壳体并禁用 Nanite。
- [x] FBX 回读核对轴向、尺寸、角色和面数；归档实际游戏月台、屋顶、场坪、铁路等近景。

### Task 2: 场地与连续周边环境

**Files:** `Tools/MPRWarehouse/build_mpr_reference_v4_site.py`, `build_mpr_reference_context_v4.py`; `SourceAssets/MPR/reference_v4/site`, `context`。

- [x] 根据参考像素反投影重建平滑道路、混凝土场坪、连续路缘、黄色车位线和白色道路标线。
- [x] 制作调蓄池与步道，完善周边灰白建筑、草地和林带，重新布置拖车、车辆和铁路货车。
- [x] 生成可编辑 Blender 总场景、PBR 纹理与空间间距报告。

### Task 3: 安全替换及验证

**Files:** `Tools/MPRWarehouse/mpr_interior_preservation.py`, `import_mpr_reference_exterior.py`, `validate_mpr_reference_exterior.py`。

- [x] 拍摄内部只读快照，备份当前地图；只删除明确属于旧外景的 Actor。
- [x] 导入版本化网格/材质，分区实例化；75036468 版本独立重载确认 136 个内部 Actor、4,441 个内部实例和 45 个依赖资产保持一致。
- [ ] 对照总览、月台、屋顶、场坪、道路与铁路截图修改视觉问题。
- [x] 完成 75036468 版本独立游戏性能采样、既有相机 API 读回与内部显示验证；归档原生 CSV、截图、统计与范围限制。
- [ ] 只提交本次已验证变更，报告中文提交标题、分支、短哈希。

## 最终复核状态

当前证据对应地图 `75036468cbea7fbbe31216514417a21937441c84abb4082ad1b42ab20369a90f`：388 个保存 Actor（136 内部、250 外部、2 相机），1,294 个外景实例（主楼 727、外场 567），66 辆拖车。源 FBX、材质颜色同步、实例位置、室内保护、实际游戏总览与八视角均已有验证证据；最终五步 UE 流程全部通过。

性能运行 `20261102_141742_352356` 为 i9-14900HX / RTX 5060 Laptop、UE 5.8.4、1920 × 1080 本地 offscreen；外景平均/P95 帧时 9.38/10.43 ms，内部 11.95/13.16 ms。每个状态预热 15 秒、采样 15 秒，内部保留 1 个 22.63 ms 尖峰，没有剔除样本。原生 CSV 的全部统计已独立重算匹配。它不代表像素流、网络、多用户或全平台测试。

项目级 Nanite 画质预算 `r.Nanite.MaxPixelsPerEdge=0.25` 未启用 VOXEL。GHS 已完成 0.25 和 1.0 各一次、预热 15 秒/运行 90 秒的原生交互对照，两次均完成 38 个动作与 2 次货物点击；本次 0.25 的平均帧时增加约 4.21%，P95 增加约 5.69%。不能宣称“对 GHS 无影响”或统计等效。

旧 V3 所有权已按递归依赖审计退役 209 个条目，文件没有删除。候选提交排除旧 V3 外景包、未引用实验 FBX、代理树、`.blend1`、缓存、备份、旧性能运行与旧 HighRes 编辑器图；以实际 game 视图归档为准。

草地和水面的周期纹理已修复；25 个场地网格几何/UV/变换与全部树车实例未改变，最终实际游戏池塘近景中不再可见旧棋盘与水面斜纹。完整 Blender 保存重开、纹理频谱与同画布原像素核验均通过。候选清单已按最终版本冻结，若后续资源/地图有变化必须刷新证据。

视觉仍有差异，20 点投影对齐不代表视觉 1:1；视觉问题项保持未勾选。提交项待实际 Git 提交完成后更新。
