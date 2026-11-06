# MPR 主 CAD 提取与设备覆盖

源文件为 `D:/Data/仓库数据/MPR/平面布局图_MPR规划图V1.1_ALL-IN-ONE_0921.dxf`。只读解析；原图未更改。

## 单位与坐标

DXF AC1032、INSUNITS=4（毫米）与实际几何冲突。标准 `RACK_42D_144B` 深42单位、总宽150单位；建筑柱距600单位，对应业主50英尺柱距。物理转换使用 **1 CAD单位=0.0254m**。原点取CAD `[12800,8000]`，布局 JSON 保持右手CAD +Y。项目现有 Blender FBX 流程以-Y forward导出，UE导入和实例变换对应 `(x,-y,z)*100`、yaw取负一次。

建筑使用 `2C93B4 / ue5u56u56` 内 `A-WALL-EXT` 外墙面的16点边界，保留端部办公室突出与东南阶梯退台，未替换成大矩形。面积56408.1891m²；364.5408×176.784m外包尺寸。外部详图和三视图不作为实体布局。

## 核实数量

- 标准货架2867：2814个144英寸横梁模块、53个192英寸横梁模块；位置无重复，全部中心在建筑轮廓内。
- 164根建筑层PILLAR；另12根设备层PILLAR保留来源记录，不混计建筑柱。
- 72个2.8448m门叶对应月台装卸门，2个3.7592m门叶对应驶入门；与业主资料一致。80个人行平开门单独记录。
- 110段配对办公室墙面提取为中心线/实测厚度；墙高不是CAD实测。
- 标准托盘位置117；另从4组3×4阵列提取48个位置。
- 标明104个充电/停车矩形只是区域轮廓，不能推出104个充电器。文字标注“12处充电桩”另存于texts；无明确机壳布局证据，不按104个矩形生成设备。

## 设备覆盖及简化

`operations/instances.json` 经2026-11-06原CAD语义复核后包含886个实例，27个模块共11792三角形（唯一模型合计，不是运行时整场面数）。使用HISM、无tick、无碰撞；材质角色对应GHS蓝白银灰。变更证据与原图解释见 `conveyor_repair_20261106/README.md`。

- 49条顶层直输送CAD模块分段为不大于2m的可复用开架模型，另根据复杂总成平行边提取干线。
- 5种弯道用实际CAD圆弧圆心、半径和旋转重建，配套支腿避免再次重复。
- 工作台、分格收集框、分拣出口、封箱/开箱、扫描架、支架由实际二维占地约束，保留开架结构；高度及内部机械细节为展示估计。164处 `terwrq434` 为人员图例、9处 `*U257/*U1667` 为箭头，独立保存在 `drafting_symbols`，不生成槽体或支架；9处重复驱动辊面合并到已有干线。
- 3条坡道复用`/Game/GHSDigitalTwin/Meshes/SM_GHS_Shared_Conveyor`；其固定坡度不适合整段水平流水线，水平模块单独制作并沿用共享材质。
- 另外三条U33弯道后的供包线由稳定原CAD边线 `operations/cad_loose_feed_geometry.json` 补回39个组件，包含两级爬升、34辊V形段、动态秤、分拣末端及中性附件。局部H标注约束范围，入口1.0→1.2→1.5m为衔接既有曲线的展示解释；后段1.5m。14个原有末端模块同步适配高度，平面位置不变，支腿落地。
- 14234123、480、小黄人三组格口支机由`equipment/`的独立CAD提取和适配模型负责，operations仅处理主干/入料和地面网格，不重复支机。96格参考装配书与CAD实际格口行列不同，不能把每支线都当成96格。
- 13条保留区域/三视图注记保存在reserved_zones。CAD仅空矩形的作业留白不生成假机器，3视图不生成多台设备。

`unmodeled_components=0`表示所有已选择顶层候选都已分类为模型、保留区、参考图或由equipment模块接管，**不意味着每个机械零件已逐一复刻**。

## 复现与验证

使用项目已存在的 `Scripts/_vendor/cad/ezdxf` 和带NumPy/Pillow的Python3.12。若在新机器重建，需自行安装这些Python依赖；本机的依赖缓存不随本次场景提交。Blender环境另需Shapely >=2.1用于环境三角化，本机缓存位置为 `Saved/ParkRefinement/python_deps`。这不影响直接导入已经提交的FBX。

所有脚本路径均相对于项目根目录 `Tools/MPRWarehouse/`。全量从原始图重建时按以下依赖顺序运行：

1. `record_mpr_source_provenance.py`：只读记录原始资料和复用的GHS生成器/参数文件的大小、路径、SHA256。执行前先与已提交的 `source_provenance.json` 比较原文件校验值；记录新校验值不等于接受新的图纸版本。
2. Python：`mpr_cad_inspect.py`（目录证据，可选）→ `mpr_cad_extract.py` → `mpr_cad_refine.py` → `mpr_cad_preview.py`（平面预览，可选）。主文件路径写在提取脚本的 `SOURCE` 常量，迁移资料位置时仅修改该路径，不修改源图。
3. Python：`mpr_cad_equipment_details.py` 和 `mpr_cad_operations_detail.py` 提取复杂设备的精简几何证据。二者内部也会调用主提取器生成本地缓存。作业设备提取固定44个已核验的源INSERT句柄，不依赖已完成实例中的“未建模”列表；可用 `--output Saved/MPR/cad-rebuild-check` 将设备证据输出到隔离目录作比较。四分格和Y汇流的稳定边线输入为 `operations/cad_detail_geometry.json`；CAD提取保留 `planar_handedness`，用于U33弯道的镜像适配。
4. Python：`extract_mpr_sorter_placements.py` → `inspect_sorter_children.py` → `finalize_mpr_sorter_placements.py`。保留 `equipment/sorter_cad_groups.json`、`equipment/sorter_child_bounds.json` 作为可复用的测量输入；最后一步补充短支机行间距摆位。
5. Python：`mpr_environment_extract.py` → `mpr_environment_align.py`。环境提取默认读取仓库内559KB的CADMapper副本；其SHA256已与用户原始环境DXF核对一致。
6. 独立后台Blender：`build_mpr_architecture.py`、`build_mpr_environment.py`、`build_mpr_rack192.py`、`build_mpr_operations.py`；分拣设备依次运行 `build_mpr_sorter.py` → `build_mpr_sorter_variants.py`。例如 `blender --background --factory-startup --python Tools/MPRWarehouse/build_mpr_operations.py`。96格参考机生成脚本读取原始装配书/照片做来源校验，所需路径和hash见 `source_provenance.json` 与 `equipment/sorter_manifest.json`。
7. Python：`verify_mpr_cad_operations.py`；独立后台Blender：`mpr_environment_validate.py`、`validate_mpr_sorter_fbx.py`。设备预览由 `preview_mpr_operations.py`、`render_mpr_sorter_variants.py`生成。UE导入/运行验证见上级 `README.md`，本节的数据再现检查不代替UE验收。

`mpr_cad_extracted.json`（约22MB）为可再生成中间证据；最终建场景使用 `mpr_cad_layout.json`。主要预览已检查，包括主平面、设备总成、作业设备对照板。`operations/verification.json`验证门柱架数量、所有FBX存在、材质槽/面数限制、实例正有限变换及无重复姿态。最终UE场景与性能由主导入/运行验证另行确认。

## 提交范围与来源追踪

`source_provenance.json` 记录用户原目录内18份DXF、图片、装配书的完整路径、文件字节数和SHA256，并将直接建模证据与其余提供的参考资料区分。AutoCAD临时锁文件不作为源资料。主CAD为 **256,076,997字节**，SHA256为 `c316aafe183162c5bef636885b59cc1000c3eecf50d8be645490b4716c6af863`；本次不复制或提交该原文件及原始照片/装配书。

精确忽略 `mpr_cad_extracted.json`、`operations/mpr_operations.blend1` 和工具目录的 `__pycache__/`。前者可由主CAD重建；后二者仅是旧保存备份和Python字节码。UE截图、日志、运行时临时报告继续放在仓库已有忽略规则下的 `Saved/MPR/`；最终验收资料由主任务选择存入 `validation/`。

以下文件虽可由源数据生成，但属于稳定建模输入、可编辑源或验收证据，**本次保留提交**：

- `mpr_cad_layout.json`、`mpr_cad_operations_lines.json`、`mpr_cad_equipment_details.json`：场景/作业模型/分拣机提取的接口；缺少operations线框会丢失实际弯头圆弧和复杂输送干线。
- `equipment/sorter_cad_groups.json`、`equipment/sorter_child_bounds.json`、所有实例清单、manifest、validation及 `scene_ownership.json`：摆位、来源和安全更新归属信息。
- `environment/environment_geometry.json`、`environment/environment_local.json`、`environment/alignment.json` 及小型环境DXF副本：可独立复现环境，无需主CAD完整展开缓存。
- 所有最终 `.blend`、`.fbx`、已检查的预览PNG、README及 `ghs_reuse_audit.md`：便于继续编辑、导入、审查和迭代。

已有GHS调色与货架参数、树车/货架生成脚本仍由原路径引用；6个直接依赖都已在Git版本管理中，其hash另记录在 `source_provenance.json`。本次不复制共享模型或缓存依赖。新机器可直接使用已提交的布局与FBX导入场景；仅当重新从原始图提取时，才需要保留在外部的256MB主CAD。
