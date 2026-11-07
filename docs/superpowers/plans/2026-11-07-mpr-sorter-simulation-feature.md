# MPR 木马播种机工作状态仿真 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 MPR 的 22 台长机上展示可操作、可核验的环行升降播种流程。

**Architecture:** 纯 C++ 确定性核心管理主链、载具、目标和箱容量；独立 UE Actor 将状态映射到几何配置与实例，原生面板控制仿真。专用开放机体与动件保留原机摆位及固定格口，资料事实与演示设定分别归档。

**Tech Stack:** UE 5.8、C++、UMG、UE Python、Blender Python/FBX、JSON。

**Spec:** [2026-11-07-mpr-sorter-simulation-design.md](../specs/2026-11-07-mpr-sorter-simulation-design.md)

## Global Constraints

- 关卡：`/Game/Maps/MPR_CAD_Warehouse_B50B57`，直接修改现有关卡。
- 仅在 `master` 开发和提交，不创建分支或 worktree，保留其他任务和用户未提交修改。
- 只处理 18 台 `cad64`、4 台 `cad120`，保留原变换与固定格口；30 台 `Short10` 不变。
- 演示默认 `BinCapacity=3`、`CollectSeconds=12`、`AutoCollect=true`，速度为 1×/2×/4×。
- 不连接真实订单、WMS/WCS/PLC；UI 标“演示数据 · 全部设备同步控制”。
- 保持 GHS 相机及主仓标签、点击屋顶溶解；MPR 仿真用独立原生面板。
- 运行布局内嵌到保存的 Actor，不能依赖 `Saved`；源码、配置和专用资产由主任务统一提交。

## Review Focus

1. 低帧率和 4× 大步长：不得跳过到站、升降、卸料、取箱事件；任务 1 验证等时分步一致。
2. 多载具命中满格：预留加占用不得溢出，清箱保留货物守恒；任务 1 验证堵塞与恢复。
3. 扫码/升降/卸料中暂停或复位：所有计时冻结，复位暂停且恢复 1×；任务 1、3 验证。
4. 镜像轴/高低格/两端转弯：商品与机构不得穿框或脱离承载面；任务 2、4 验证实际网格和运行路径。
5. 范围绑定失配或重载：不得误改短机、共享原资产、无关 Actor；任务 3、4 验证前置拒绝与保存重载。

---

### Task 1: 确定性播种核心

**Files:**
- Create: `Source/Test/MPRSorterSimulation.h`、`Source/Test/MPRSorterSimulation.cpp`
- Test: `Source/Test/Tests/MPRSorterSimulationTests.cpp`

**Interfaces:**
- `MPRSorter::Config` 输入厘米制环长、站点归一化距离、层高、容量、速度及演示目标序列。
- `bool Simulation::Initialize(const Config&, std::string& Error)`；`bool Advance(double WallDeltaSeconds)`。
- `SetPlaying(bool)`、`Reset()`、`bool SetRate(double)`、`SetAutoCollect(bool)`、`bool ClearBin(Destination)`。
- `GetCarriers()`、`GetBins()`、`GetStats()` 输出只读状态，供任务 3 消费；`CarrierCount=4`。

- [x] 写配置缺失/非有限值/非法目标的失败测试，要求初始化拒绝时原状态不变。
- [x] 写共享 1/4 相位、活动 ID 唯一、容量预留、两条货物守恒式及全格可达测试。
- [x] 写满格停链、清箱恢复、自动取箱开关、暂停/复位/速率和到层后才卸料测试。
- [x] 写 `173.125s` 不同分步一致与 `900s × 4` 等价 `36000 × 0.1s` 测试；NaN/极大步长拒绝且状态不变。
- [x] 实现事件边界推进，完成一次卸料才计数；共同链停靠与各托盘独立升降分开处理。
- [x] 对 `Reserved>0` 格口拒绝手动取箱、延后到期自动取箱；验证过期计时不会导致零步长死循环，入箱与取箱边界保持守恒及分步一致。
- [x] 构建后运行 `MPR.Sorter` 全组，要求全部通过并保存报告；现有 `automation/index.json` 记录 10 项通过，包含两项取箱互锁测试与任务 3 的 `LayoutValidation`。

构建使用经命令级授权的 `D:/UE/UE_5.8/Engine/Build/BatchFiles/Build.bat TestEditor Win64 Development D:/UEPro/Test/Test.uproject -WaitMutex`。自动测试入口：

```powershell
& 'D:/UE/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe' 'D:/UEPro/Test/Test.uproject' -unattended -nop4 -NullRHI '-ExecCmds=Automation RunTests MPR.Sorter' '-TestExit=Automation Test Queue Empty' '-ReportExportPath=D:/UEPro/Test/Saved/MPR/sorter_sim_20261107/automation'
```

通过条件为报告中所有 `MPR.Sorter` 测试成功，不能仅凭进程退出码判定。

### Task 2: 保留外壳的机械资产与标定

**Files:**
- Create: `Tools/MPRWarehouse/build_mpr_sorter_sim_assets.py`、`Tools/MPRWarehouse/verify_mpr_sorter_sim_assets.py`
- Create: `SourceAssets/MPR/sorter_simulation/layout.json`、`manifest.json`、`MPR_SorterSimulation.blend`、专用 FBX/LOD
- Create: `SourceAssets/MPR/sorter_simulation/research/README.md`、`evidence.json`、四张关键原图
- Read: `SourceAssets/MPR/equipment/sorter_instances.json`、既有可编辑设备模型和关卡快照

**Interfaces:**
- `layout.json` 输出 `machines` 的 GUID/组件/实例/变换/源句柄，`profiles` 输出厘米制轨道、托盘、所有格口的滑槽入口/出口及箱底/箱沿。
- `manifest.json` 输出 FBX 路径、哈希、边界、三角面、材质角色与 LOD；任务 3 只导入此清单中的专用资源。

- [x] 从既有模型量测 22 台、两型机各格口，记录原包哈希与原变换；拒绝缺失或歧义绑定。
- [x] 建立完整环路、两侧和高低层采样检查，移除占用动件通道的假长带与实心端柜。
- [x] 构建开放机体、移动立柱、短带托盘；固定格口/箱角坐标保持原样，保留材质角色并生成 LOD。
- [x] 运行独立 Blender FBX 回读检查：`& 'D:/WinAPP/Blender/blender.exe' --background --factory-startup --python Tools/MPRWarehouse/verify_mpr_sorter_sim_assets.py`；`geometry_validation.json` 记录 `status=passed`、8 个 FBX 回读及 41,984 个托盘姿态零 AABB 交叠。
- [x] 记录上下导轨接触面与障碍排除规则；核实轴转换只发生一次、完整外廓不越界。此检查不证明全姿态制造间隙达标。
- [x] 归档手册图 16、17、22 及原文证据，明确 96 格、厂商最大值、场景既有配置和演示参数的边界。

### Task 3: UE Actor、独立面板与原关卡接入

**Files:**
- Create: `Source/Test/MPRSorterSimulationActor.h/.cpp`、`Source/Test/MPRSorterHUDWidget.h/.cpp`
- Create: `Tools/MPRWarehouse/apply_mpr_sorter_simulation.py`、`verify_mpr_sorter_runtime.py`、`test_mpr_sorter_apply_scope.py`
- Test: `Source/Test/Tests/MPRSorterLayoutTests.cpp`
- Modify: `Content/Maps/MPR_CAD_Warehouse_B50B57.umap`
- Create: `Content/MPRWarehouse/SorterSimulation/` 下专用资产

**Interfaces:**
- Actor 消费任务 1 状态与任务 2 布局；保存 `LayoutJson`、`TowerMesh`、`TrayMesh` 和包裹资源引用。
- UFUNCTION：`SetSimulationPlaying(bool)`、`ResetSimulation()`、`SetSimulationRate(double)`、`SetAutomaticCollection(bool)`、`ClearFullBins()`、`FocusMachine(int32)`。
- `GetSimulationReportJson()` 输出可核验状态；`AdvanceSimulationForDiagnostics(double)` 仅在 `-TwinDiagnostics` 下生效。

- [x] `LayoutValidation` 验证真实 22 台/1,632 格及缺 profiles、空变换、空层对象、重复格口四种损坏输入；失败不能留下部分设备或覆盖原有效布局。
- [x] 运行 `test_mpr_sorter_apply_scope.py` 的 9 项离线范围测试，验证变换漂移、短机材质、无关 Actor、相机及烘焙运行实例越界修改均被拒绝；应用脚本执行写入前预检。
- [x] 实现一台控制 Actor，按既有变换定位固定体和动件；运行只消费已序列化配置，不读取临时 Saved 文件。
- [x] 将立柱、升降托盘和包裹分别实例化，按共享链相位更新；包裹到层、到列且有容量后才进入固定槽。
- [x] 新增 MPR 面板并接入上述 API，显示“演示数据 · 全部设备同步控制”、选中设备统计与等待原因，定位调用现有相机。
- [ ] 通过真实 OS 鼠标验证面板按钮点击及事件不泄漏到场景。授权超时，当前未实测；不得用 API 检查代替。
- [x] 源码确认诊断时间推进受 `-TwinDiagnostics` 限制；原生 API 测试中间阶段暂停/复位和“自动取箱关闭 → 满格等待 → 清满格 → 恢复”。
- [x] 原生运行验证 GHS 屋顶打开、总览恢复与复用相机定位；范围检查确认其他 Actor/包保持原样，不声称执行了全部 GHS 自动化回归组。

### Task 4: 保存、运行与交付验证

**Files:**
- Validate: 任务 1–3 文件、原 MPR 关卡及专用资产包
- 原始验证输出：`Saved/MPR/sorter_sim_20261107/`，包含全部阶段图、帧序列与临时日志。
- 交付证据：`SourceAssets/MPR/sorter_simulation/validation/`，归档通过的范围报告、重载/自动化结果、两张高层图、工作流短片及性能采样；不提交缓存、原图备份或逐帧临时图片。

**Interfaces:**
- `apply_mpr_sorter_simulation.py` 的 `verify_only` 分支核对独立重载；当前实际入口是不传 `-MPRSorterApply`，并非另一个验证脚本。
- `verify_mpr_sorter_runtime.py` 运行原生 API/实例回读、定帧图及帧率测试，用 `GetSimulationReportJson()` 读取核心与可见实例状态。

- [x] 对比改前快照和保存后关卡：3 个目标 HISM 组的 22 台变换不变，883 个其他 Actor、1,905 个原 Content 包保持原样，30 台短机不变；只新增 1 个控制 Actor 和 5 个专用 Content 资产。
- [x] 独立进程重载保存关卡，验证内嵌布局和资产引用；`application/reload_report.json` 成功，当前地图及 5 个新资产哈希匹配保存报告。
- [x] 两型机两侧高低层原生截图和实际实例位姿回读通过；四段倾斜投料及 16,016 次截面采样未穿托盘/槽/箱口，维持工作流程动画的验证范围。
- [x] 在 1920×1080 下留下 3 张固定机位阶段图、8 张定向卸料图及 96 帧序列；原生 API 检查开始/暂停、1×/2×/4×、定位、满格、清格和复位通过。
- [x] 记录本地原生近景、22 台自动 Tick 和 HUD 可见条件下约 15 秒/1,879 帧：平均 125.32 FPS，P95 帧时 9.71 ms。该数据不代表全景、独占硬件、生产吞吐或流媒体并发测试。
- [x] 审查并暂存本轮源码、输入、必要资产、原关卡和选定交付证据；未暂存 DefaultEditor.ini 与共享 PaleGray 材质的既有修改。
- 提交记录：本文件随本轮 `master` 中文本地提交归档；实际哈希以 Git 历史和完成回复为准。

本计划用于已授权任务的执行与复核。未勾选项表示需要关联实际验收证据，不表示已失败，也不构成新的用户审批要求。

核验记录：2026-11-07，自动化 `Saved/MPR/sorter_sim_20261107/automation/index.json` 为 10/10 通过；应用与重载报告位于同目录的 `application/`；`runtime/report.json` 本轮 `20261107T043513235298Z` 为 13/13 检查通过。OS 鼠标验证仍未完成，交付说明已记录应用授权超时。
