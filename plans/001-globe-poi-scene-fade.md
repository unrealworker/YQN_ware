# 001 — 全球 POI 随入仓与返回淡入淡出

- **Status**: DONE
- **Commit**: 18d64ee
- **Severity**: MEDIUM
- **Category**: Missed opportunities / Interruptibility / Accessibility
- **Estimated scope**: 原生覆盖层、全球控制器、原生测试，共约 5 个文件。

## Problem

`D:/UEPro/Test/Source/Test/GHSGlobeNavigation.cpp:493` 当前直接清空原生点线卡片：

```cpp
const bool Visible=bStageVisible&&(Phase==EPhase::Idle||Phase==EPhase::Selected||Phase==EPhase::Loading||Phase==EPhase::Error);
if(!Visible){WarehouseOverlay->SetMarkers({});return;}
```

网页其他内容已在退场，原生标注却瞬间消失。入仓/返回属于偶发操作，透明度过渡可交代状态切换。

## Target

- 入仓原生点、线、卡片统一 opacity 1→0，160ms。
- 返回统一 opacity 0→1，180ms；仅在全球舞台和有效投影恢复后开始。
- 精确使用现有 standard 曲线 `cubic-bezier(.4,0,.2,1)`，原生代码需正确求解曲线 x→y，不能以参数 t 直接替代 x。
- 减少动效使用 120ms 透明度；键盘触发不添加本次视觉延迟。
- 退场一开始关闭按钮交互；退场期间继续按本帧相机更新锚点和布局，不能缓存屏幕坐标。
- 初始显示、拖拽、缩放、标签进出视野、选择切换不触发整组淡入淡出。
- 中途恢复从当前 alpha 接续；世界隐藏、投影失效时立即清理，不显示背面或仓库中的旧标注。动画不能延迟场景状态机。

## Repo conventions to follow

- UI 标准曲线在 `D:/UEPro/Test/Content/GHSTwinUI/web/globe.css:1`：`--ease-standard:cubic-bezier(.4,0,.2,1)`。
- `SGHSGlobeWarehouseOverlay.cpp` 已统一绘制点线卡片并取消 DPI 对像素尺寸影响；保持白圈20px、核心15px。
- 当前分支固定 master，不创建 worktree。

## Steps

1. 在 `D:/UEPro/Test/Source/Test/SGHSGlobeWarehouseOverlay.h/.cpp` 增加可中断、按目标状态启动而非每帧重启的统一透明度控制及独立交互开关。
2. 在 `D:/UEPro/Test/Source/Test/GHSGlobeNavigation.cpp` 接入入仓/返回阶段；绘制退场期间继续实时投影。
3. 为方案002提供选择输入来源：原生按钮区分 pointer/keyboard；控制器接受命令 `inputSource` 并输出 `selectionInputSource`（pointer/keyboard/unknown）。旧命令继续有效。不得对原生按钮增加方案外按压动画。
4. 在 `D:/UEPro/Test/Source/Test/Tests/GHSGlobeOverlayTests.cpp` 添加时序、反转、交互禁用、真实按钮输入来源测试。

## Boundaries

- 不改世界锚点、避让、固定像素尺寸、地图、相机路径、飞行/遮罩/流送时长、国家名称。
- 不改其他仓库场景功能和用户未提交的 MPR 关卡/曝光脚本。
- 不加依赖、不做持续呼吸/光圈/引线生长、不对坐标做动画。

## Verification

- Mechanical: 通过授权入口 Build.bat 编译 TestEditor；运行 `Automation RunTests GHS.Globe.`，新增与原有测试均通过。
- Feel check: 独立离屏全球关卡中以真实 pointer 命令进入/返回，逐帧记录前 180ms；确认点线卡片 alpha 一致、锚点仍随相机、无尾影穿入仓库。检查减少动效、键盘来源和快速取消。
- Done when: 160/180ms时序通过原生测试，真实运行进入/返回成功，固定像素和地理投影回归通过，地图文件哈希不被测试改写。

## Result — 2026-11-06

- TestEditor 最终编译成功；`GHS.Globe.` 原生自动化 18 项通过，0 失败。
- 独立 1920×1080 运行完成普通鼠标、减少动效鼠标、键盘三组入仓/返回；前两组出现预期中间透明度，键盘即时切换，退场按钮立即失效。
- 已检查真实渲染过渡帧，点、引线、卡片同步变化；测试前后关卡文件哈希一致。
- 复查修复非激活输入残留来源；新增真实按钮回归断言通过。
