# MPR 植被与地坪重排 Implementation Plan

> **For agentic workers:** 按本会话已授权的原关卡协作方式执行，各生成任务独立检查，主执行器负责 UE 写入和提交。

**Goal:** 使主仓植被形成清晰边界，外围树列和自然树群有序，绿地与硬质地坪衔接完整。

**Architecture:** CPU 几何规划生成树实例与地坪数据，Blender 后台导出局部绿地/路缘网格；主执行器仅变更审核通过的现有 Actor 字段，在保存前后独立比较全部场景。

**Tech Stack:** Python、Shapely、Blender 5.2 后台、UE 5.8 Python 与 HISM。

**Spec:** `docs/superpowers/specs/2026-11-06-mpr-landscape-design.md`

## Global Constraints

仅 master、原 MPR 关卡；保留用户手动状态和所有无关资产；固定相机与分辨率。

## Review Focus

- 道路布局使用最新删除修复后的数据，不让已删路重新出现。
- 树冠让开建筑、道路、轨道、车辆及作业空间。
- 绿地/路缘贴合已有地形，不改变排水坡度或生成白色重叠面。
- Blueprint HISM 重建后必须读回实例、材质与颜色标记。
- 独立重载确认全场景状态，避免只验证编辑器内临时效果。

## Task 1: 树与地坪几何规划

**Files:** `Tools/MPRWarehouse/plan_mpr_vegetation_layout.py`、`plan_mpr_landscape_ground.py`、`build_mpr_landscape_ground.py`；`SourceAssets/MPR/landscape_layout_20261106/`。

**Interfaces:** 输入实时 baseline 和最新交通/地形来源；输出树 GUID/组件目标、完整实例变换及 custom data，绿地多边形、FBX 网格映射、源哈希与几何检查报告。

- [x] 建立当前树/地坪诊断与保护遮罩。
- [x] 生成三层植被和连续绿带，并用二维布局图核对。
- [x] 验证树冠净距、地形支撑、绿面边界、材料槽及 FBX 回读。

## Task 2: 原关卡应用与验收

**Files:** `Tools/MPRWarehouse/mpr_landscape_layout.py`、`capture_mpr_landscape_layout.py`；现有 MPR 地图和专属新资产。

**Interfaces:** `run(unreal)` 只处理规划清单中的字段；`verify_reload(unreal)` 在独立 commandlet 检查保存结果。

- [x] 以操作前实时快照验证预条件并保存可恢复快照。
- [x] 导入新网格、重排既有树实例，检查非目标 Actor 完整保留后保存原地图。
- [x] 独立重载并按同机位截图审视全景、主仓绿带和转角，必要时局部修整。
- [x] 归档验证与帧率，审核差异后在 master 创建中文本地提交。
