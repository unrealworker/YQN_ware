# 仓库地址与当地时钟实施计划

> **For agentic workers:** Use executing-plans for implementation, with independent design work and final review. User has approved implementation and committing to master.

**Goal:** 将已确认的地址与仓库当地实时时钟同步到正式设计和原生顶部栏。

**Architecture:** 现有 Slate HUD 绘制双行地址和时钟。时间从系统 UTC 经引擎 ICU 的 America/Los_Angeles 转换，每个 UTC 秒刷新一次，日期、PDT/PST 和偏移保持一致。窄屏顶部栏分行且输入区域同步布局。

**Tech Stack:** UE5.4 C++ / Slate / ICU / Pencil。

**Spec:** `DesignPreviews/GHS_Address_Time/ghs-address-clock.html`（用户已确认）；正式设计 `Design/GHS_Twin_SaaS_Concept/Saas.pen`。

## Global Constraints

- 地址：17335 Glen Helen Pkwy / San Bernardino, CA 92407 美国。
- 显示：仓库当地时间 HH:mm:ss；YYYY.MM.DD · PDT (UTC−07:00)，冬季自动 PST (UTC−08:00)。
- 保留主仓库 POI 及既有屋顶、设备交互；不恢复“普通仓库”文案。
- 覆盖正式设计及当前导出；保留用户既有未提交修改；中文提交到 master。

## Review Focus

- UTC 换日与当地换日不同，时间和日期必须同一时区。
- 春秋 DST 边界、冬季、夏季不能使用固定偏移。
- 系统时钟倒调仍立即刷新；暂停游戏不暂停墙钟。
- 分辨率缩小或高 DPI 下地址、时钟、面板按钮不能互相遮挡。
- 顶栏分行后不能让地址点击触发右侧面板开关或选中场景。

## Task 1: 正式设计同步

- [x] 使用 Pencil 更新所有当前相关顶栏及共享组件，覆盖 current 导出。
- [x] 核对截图、长文本边界、文件和设计说明。

## Task 2: UE 实现与验证

- [x] 新建 GHSWarehouseClock.h/.cpp 与日期、DST、刷新行为自动化测试。
- [x] 新增共用顶栏布局，在 GHSTwinLayout / GHSTwinHUDWidget 中绘制并同步命中区域。
- [x] MSVC 14.38.33130 编译 TestEditor 和 TestGame，111 项 GHS 自动化通过。
- [x] 实际运行核验每秒刷新、顶部信息排布及面板开关，保留截图。
- [x] 独立代码审查、核对 diff，中文提交 master。

## 执行记录

- 基线：92a9fab。用户已授权更新和开发，不另设确认步骤。
- 设计与时区逻辑分别委派；主代理负责 HUD 整合、编译及验收。
- RED：4 项时区测试因未实现的空值/刷新返回值失败；GREEN：最终 111 项 GHS 测试全部通过，无失败或警告。
- 独立审查未发现需修复项。实际截图发现字体缺少 U+2212，渲染使用普通连字符后复验通过。
- `Saved/AddressClock/runtime.json` 最终 success=true，6 项场景检查通过。用户地图文件未改变；原有未提交文件未纳入提交。
