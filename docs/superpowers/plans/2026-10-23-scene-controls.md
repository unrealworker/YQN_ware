# 场景图层、库容与道路端口 Implementation Plan

> **For agentic workers:** Use subagent-driven-development for independent asset/design tasks; root integrates and verifies.

**Goal:** 实现已批准的四图层即时控制、80%/100%库容滑条与贯通道路端口，更新正式设计。
**Architecture:** 离线生成完整可控货物，运行时实例化/材质阈值控制；HUD负责屋顶和定位时序，数据层负责可见性及拾取；前端合并滑动事件。
**Tech Stack:** UE5.4 C++/Python, Blender, HTML/JS, Pencil.
**Spec:** `DesignPreviews/scene-controls-20261023/proposal.md`，用户2026-10-23已批准；开启蓝色#356BFA。

## Global Constraints
- 已授权master开发并中文提交；保留已有未提交文件与手动地面材质。
- 固定现有32实例车流，不改库存核验数据，不打包或启动像素流。
- 货架0时保留钢架，地堆按双蓝托盘整组变化；稳定槽位，恢复不重新随机。
- 闭顶与0.5秒开顶期间不可显示内部标签或拾取；最后操作优先。
- 滑动每秒最多30条中间值，松手最终值立即发送；无每次拖动重建HISM/Actor。

## Tasks / Interfaces
1. 正式设计：`Design/GHS_Twin_SaaS_Concept/Saas.pen`及当前导出/索引，保留业务页。核对节点、截图和源文件已保存。
2. 库容资产与组件：独立`GHSStorageCapacityComponent`，提供SetCapacity(rack,floor)、SetStorageVisible(bool)、IsStorageHitVisible(component,instance,point)、GetReportJson；运行时完整货物实例和独立钢架；资产构建/导入脚本可复现。父任务调用接口。先提交接口声明说明，再实现并几何验证。
3. 道路端头：局部移除原道路端帽、保留侧沿，生成专用补丁和导入脚本；父任务统一运行UE资产写入。几何开口测试与前后实景。
4. HUD/网页联动：四开关、滑条、取消应用按钮、恢复默认、同步快照、清除隐藏选择；库容组件与SceneData拾取联动。测试默认、限流最终值、反向切换、闭顶锁和定位恢复层。
5. 编译与验收：MSVC14.38.33130，UE自动化/网页测试、实际0/default/100和往返拖动对比Game/Render/GPU与长帧；场景截图和设计截图。
6. 独立审查，修复问题，归档证据，中文提交master。

## Review Focus
- 隐藏后业务刷新/搜索定位不得无意重新显现或选中。
- 开顶延迟回调不得覆盖最后一次图层、复位、默认或定位操作。
- 完整货物不是Occ70放大；100%真实全量，0%钢结构完整。
- 货物隐藏同时影响阴影、LOD、CPU拾取；30Hz不重建场景。
- 道路修补不影响现有路面/用户地面材质/车流路径/园区围栏。

## Progress
- [x] 读取批准方案，确认master已授权；基线3f94ed8。
- [x] 资产与道路独立实现；设计画布和导出完成。
- [x] 前后端与容量接口集成。
- [x] 编译、功能与性能验证：114 UE / 85 Web；实际CEF+GPU四段采样及近景阴影检查。
- [x] 独立审查及验收归档，见 `docs/scene-controls-validation-20261023.md`。
- [ ] Pencil源文件保存：Windows锁屏，已请求用户解锁；画布保留，禁止将导出当作源文件已保存。
- [x] 开发、资产、导出与验收记录纳入本次master提交；保留无关更改，原生设计保存待解锁后补交。

Ruling: 使用现有工作目录执行，避免UE二进制与编辑器上下文在新工作树丢失；逐路径暂存保留无关更改。
