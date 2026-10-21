# 下拉筛选菜单偏移修复

库存“全部货位”和订单“全部状态”的原生菜单在 UE 中向左上方偏移。已在用户 UE 预览中复现：按钮约在 y=682，菜单约在 y=500。

共用 HTML select 的菜单由 UE CEF / Slate 弹窗处理，位置跨越浏览器 CSS 坐标和 HUD DPI 缩放坐标。修复将共用筛选改为页面内 listbox，以按钮的 getBoundingClientRect 定位，避免跨坐标系弹窗。没有修改引擎、原生 HUD DPI、画质或已完成的 P0/P1 优化。

覆盖库存状态、订单状态、设备类型、设备状态（含充电设施）与告警级别。保留原 change/data-filter 筛选路径；支持选择勾选、方向键 / Home / End / Enter / Escape / Tab。菜单在边缘自动翻转并限制高度；外部点击、滚动、缩放、切页或面板隐藏会关闭菜单。菜单打开时延后遥测 DOM 刷新，关闭后消费最新数据，不新增常驻布局测量。

验证证据：

- 全部 Web Node 测试 51/51，通过记录：Saved/DropdownFix/node-tests.log。
- 真实浏览器 22 项几何及关闭检查通过，覆盖 480×1016、360×640、600×420 等视口与 1 / 1.5 / 2 倍设备像素密度；所有菜单均与按钮保持 6 CSS px 间隔，包含向上翻转与高度截断。记录：Saved/DropdownFix/browser_acceptance.json。
- 独立 UE 5.4 / CEF 实例在 1920×1080 下，全部五个控件的鼠标打开、键盘选择及 Escape 验证通过；滚动事件、隐藏和导航关闭检查通过。记录：Saved/DropdownFix/cef-acceptance.json。
- 实际 CEF 截图已人工检查：Saved/DropdownFix/cef-inventory.png、cef-orders.png。
- 独立代码审查未发现阻断问题；git diff --check 通过。

本次仅网页资源变更，不需要 C++ 重编译。新脚本已由 Test.Build.cs 既有 web/... NonUFS 规则纳入下次打包。当前已打开的旧页面需要重新进入 Play 才会加载新资源。

已同步四个变更网页文件到本线程此前交付的 `Saved/PerformanceP0P1/OptimizedBuild/Windows/Test/Content/GHSTwinUI/web`，逐文件 SHA-256 一致；冻结基准包保持不变。该同步为 NonUFS 网页资源更新，没有重新执行完整 cook / build。
