# MPR 全部输送线复核（2026-11-07）

已覆盖 886 个操作区实例，886 个精确映射到快照 Actor/HISM 索引。直线滚筒实例 411 个，合并来源 75 组。

## 确证问题

- **F01** 108 crossed-rectangle CAD placeholders were fabricated as computer worktables. Adjacent 3x3 placeholders become a continuous white raised slab with nine screens. Replace only these 108 instances with flush CAD cross-outline markers, preserve positions/rotations; exact operational use unconfirmed.
- **F02** 2E7F10 local CAD long axis X was mapped to GHS conveyor width X, while GHS travel axis is Y. Direct XY bbox scaling produces a wide short roller table with wrong roller/travel direction. Dedicated geometry with actual 2E7CE9 belt boundary (2.42179 x .8m), source outer frame and X travel axis.
- **F03** All three source supply ramps use an unrelated generic GHS roller conveyor; the source supply-ramp drawing shows a belt and side-guides. 3D incline heights are not established by 2D CAD. CAD footprint + continuous belt + display-only incline; preserve source XY and do not invent inter-machine links.
- **F04** The illustrated supply ramps are isolated in the original CAD too. There is no drawn connecting conveyor through the gap to the main line or compact machine head. Keep source location; transport across gap needs manual handoff or documented equipment, not nearest-neighbour bridge.
- **F05** Named wheel sorters (20 M5A10 + 2 BAILUN) are represented by generic straight roller modules; the CAD name and detailed plan indicate transfer/sorting modules. Mark as transfer device; route behavior remains unconfirmed, never treat as unidirectional straight through line automatically.

## 截图对象精确定位

- ['2CCF62'] ['供包爬坡'] CAD坐标 [-107.37526, 2.00169, 0.021]，MPR_SM_GHS_Shared_Conveyor_-2_0 GUID 29EF93E64FEB0131B94451970F955F72，HISM 索引 0。
- ['2CCF66'] ['供包爬坡'] CAD坐标 [-101.13565, -28.05388, 0.021]，MPR_SM_GHS_Shared_Conveyor_-2_-1 GUID 7280F6BF4C31FF0210FF73937691AAD3，HISM 索引 0。
- ['2E7F10'] ['供包爬坡机'] CAD坐标 [-104.26005, -36.84552, 0.021]，MPR_SM_GHS_Shared_Conveyor_-2_-1 GUID 7280F6BF4C31FF0210FF73937691AAD3，HISM 索引 1。

白平台：2D437C..2D4384 等 A$Cb1177cf1 对应的紧邻3×3叉格。原图只有矩形加叉线，不能建成带屏幕桌面。全场同类108个一并修正。

## 拓扑和证据边界

- **2C9A89** CAD central assembly location [-104.28999,-13.00301]; current long roller axis x=-104.3,y=-31.05301..5.04699 is hard-coded visual simplification. Supply ramps are offset and not connected in CAD. Individual 18 machine ports require component-level proof; do not use box centre as port.
- **2C9AE5** CAD assembly centre [-111.52478,16.36737]; current central roller x=-111.52,y=12.31737..20.41737 is hard-coded visual simplification. PW_TG_96C_IN contains infeed structure but its existing worktable placeholder is not a trustworthy endpoint. Four machine ports need component-level evidence.
- **2D41B7** Ground grid not a conveyor; isolated 2E7F10 infeed remains separated; do not join every short row to grid.
- **heights** All basic rollers use display height 1.0m, feed rows H1200/H1500 based plan labels use 1.2/1.5m assumptions, no source elevation guarantees. Generic GHS slopes must not define operational transfer height.
- **coverage** Every operation instance classified/mapped; source-derived surface connectivity reviewed, PLC flow, height, speed and safety logic not specified by plan.

## 禁止推断

- 不将最近几何端点自动认定上下游。不跨越通道补传送带。不将650mm地面方格或321321容器框当输送段。
- 不宣称所有矮排设备均为独立机器；须分开主机和可更换容器车。
- 输送方向、准确高度、速度、满载条件、换车锁定需以设备资料补足；当前平面CAD不能独立证明。

## 取证文件

- conveyor_audit.json：全部886实例、Actor GUID、HISM索引、源handle，和完整直线来源分组。
- cad_context_user_region.png：用户图区域源CAD叠图，证明供包台原图孤立。
- cad_2CCF62.png / cad_2CCF66.png / cad_2E7F10.png：三台源供包爬坡原图。
- cad_2D437C.png：误桌面源符号，仅外框和对角叉。
