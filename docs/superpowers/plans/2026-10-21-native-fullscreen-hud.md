# 本地 EXE 全屏与高分辨率 HUD 修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 直接启动 EXE 时即以本机桌面分辨率全屏显示，并让 2560×1600 的 HUD 保持合理尺寸和正确交互。

**Architecture:** 游戏窗口创建之前确定默认显示模式；开启 UE 游戏高 DPI 支持。HUD 统一使用设计坐标，投影和鼠标只在边界转换一次。

**Tech Stack:** UE 5.4、C++、Slate/UMG、嵌入式 WebBrowser，MSVC 14.38.33130。

**Spec:** 本次用户要求：本机 2560×1600；直接启动 EXE 不应反复改变尺寸；默认全屏；暂不验证像素流启动。

## Constraints and review focus

- 在 master 完成并中文提交；保留无关 Samples/。
- 不保存或改变场景资产，不改变已批准的界面视觉风格。
- 默认行为在实际游戏窗口创建之前生效，不用 BeginPlay 再切换全屏。
- 保留显式 windowed、ResX/ResY、RenderOffscreen 参数，以及编辑器/PIE 行为。
- Windows 150% 缩放不得与 HUD 设计缩放重复相乘。
- POI、选中框、鼠标命中、搜索输入和 WebBrowser 面板保持同一坐标规则。
- 当前任务只进行本地 EXE 验收；保留用户正在运行的像素流服务。

## Tasks

- [x] 从无参数启动日志、引擎创建窗口流程、现有 HUD 缩放代码验证根因。
- [x] 实现高 DPI 与默认全屏启动策略，覆盖显式参数和编辑器边界。
- [x] 实现 HUD 设计坐标转换，覆盖 1080p、2560×1600、4K 和小窗口。
- [x] 编译 TestEditor，运行 GHS 自动化；构建可独立运行的新包。
- [x] 无分辨率参数启动打包 EXE，检查首次窗口尺寸及 2560×1600 界面、搜索、POI 和侧栏操作。
- [x] 复核差异与证据，中文提交 master，报告新 EXE 位置。

## 验收记录

- TestEditor 和 Development Windows 打包均 exit 0；地图 SHA256 未改变。
- GHS 自动化 101/101 通过；业务页面 Node 测试 57/57 通过。
- 无参数直接打开本地包：首显 client=2560x1600、mode=1；前 10 秒 shapeChanges=0。
- 最终包初始 GHS_OVERVIEW_FRAME 只有一次，逻辑视口 1920×1200、距离 73333.3。
- 实际 UE CEF（Windows DPR=1.5）验证侧栏 480 设计宽、5 类下拉锚定及键盘筛选、设备详情固定操作栏，共 7 项通过。
- Windows 实际输入 AGV 查询返回 32 项，点击 AGV-01 后定位到充电区对应模型。
- 本地交付：Deployment/LocalWindows/Windows/TestGame.exe；此次不验证或替换运行中的像素流服务。
- 构建记录：Saved/PixelStreaming/Packaging/package-20261021-171223.result.json。
- 运行证据：Saved/NativeDisplayFix/packaged-final-runtime.log、Automation/index.json、cef-report.json。

CEF 5.4 的 file:// 样式表不能通过 CSSOM 读取，旧 Chromium 的 CSS zoom 也不能提供可靠缩放后 DOMRect。最终用根元素 transform 和按逻辑尺寸计算的 data-layout 条件同步面板，已在真实 CEF 验证下拉框和固定操作栏。
