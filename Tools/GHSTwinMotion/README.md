# UE 实际页面动效与图表

这是 `Content/GHSTwinUI/web` 的离线增强构建源，**不是独立 React 设计原型**。保留原页面状态机、UE 桥接、核验数据及追溯交互；React Bits CountUp 作为数字组件，Apache ECharts 负责环图、堆叠进度、状态/类型柱图与订单趋势。

## 构建

```powershell
cd D:\UEPro\Test\Tools\GHSTwinMotion
npm ci --cache D:/UEPro/Test/Saved/npm-motion-cache
npm run build
npm test
node --test ../../Content/GHSTwinUI/web/tests/*.test.js
```

锁定 React 19.3.1、Motion 12.43.0、ECharts 6.1.0、esbuild 0.28.2。构建目标 Chromium 90，输出本地 `motion.js`、`motion.css` 和许可文件。UE 现有 NonUFS 规则会一同打包，运行时不需要 Node、CDN 或外网。

## 动效规则

- 导航选中高光在接受点击或键盘激活的同一事件中更新，早于 UE 桥接通知；使用独立合成层 `translate3d`，180ms，`cubic-bezier(.16,1,.3,1)`。连续切换从当下位置重新指向最新目标，不排队，不插入等待，不动画宽高。
- 悬停只显示按钮自身的淡蓝背景，100ms；不移动选中高光。按下仅图标和文字缩放至 0.96，70ms；松开 140ms 恢复。键盘聚焦继续使用原有焦点框。
- 追溯中的离开确认通过前保持当前导航选中项；取消离开不切页。重复点击当前页面不会重播整页过渡，仍会刷新已经变化的业务数据。
- 页面内容使用一层淡入淡出：退出 80ms，进入 140ms，总计 220ms。导航始终可交互，退出期间以最后一次目标为准；进入期间也可中断。移除原来整页过渡叠加 300ms / 最长 210ms 错峰造成的二次等待。
- 语义指标首次直接显示实际值，不从 0 重播；只有数据真正变化时才懒创建 React Bits 组件，从当前显示值在 240ms 内过渡。一次刷新只使用一个 React 提交边界，保留逗号、负数和小数。编号、时间、样例明细和未知值保持原文。
- 冷页面首先显示完整的 SVG/HTML 图表；220ms 页面过渡结束后，每帧最多增强一个 ECharts 实例，静态交接不再从空白展开。后续数据更新保留 240ms 插值、提示和高亮。
- 字体就绪、启动遮罩仍未揭开时准备实际台账图表，随后移除临时页面节点，把该实例放入同一有界缓存；首次进入设备页直接复用，避免在点击后承担 CEF 文字测量和分类轴初始化成本。
- 只有同一视图中新出现的列表条目轻移 4px、160ms 淡入，条目间隔 20ms、最多延后 60ms。页面切换不再给父容器和子条目同时入场；已有条目在遥测刷新时不重复入场。
- 最多缓存最近 8 个视图的数字与图表，覆盖七个主页面及最近详情。返回时复用已有实例；同页刷新同步重新挂接。离屏实例结束动画并取消尺寸观察，淘汰时释放资源。变化数据才调用 setOption，不变数据不重播。
- 导航中取消未初始化的旧页图表队列；隐藏面板时取消待执行帧，并同步解除页面过渡锁，恢复时使用最新视图和数据。图表收敛不再全量重设 options；缩放仅在实际尺寸变化时重新布局，柱图单独更新文字留白。
- 面板隐藏、页面后台或减少动画偏好开启时立即收敛，清理动效。导航仅在实际按钮几何变化时即时校准，未改变几何的 DPI / 视口通知不会打断高光。图表按真实布局尺寸响应，避免 UE CEF 百分比尺寸误读。
- 保留 SVG/HTML 静态回退和现有数据未核验提示，未接入任何新数据源。

## 验证

`Scripts/ghs/verify_ui_motion_runtime.py` 在单独的 `-game -RenderOffscreen -TwinDiagnostics` 进程验证真实 CEF，不修改或保存地图。截图和运行报告写入 `Saved/UIMotion/`。页面诊断在 `window.TwinMotion.diagnostics()`，原生报告包含 `motion` 字段。

`Scripts/ghs/verify_ui_motion_performance.py` 在相同环境记录冷/热切页、连续导航、数据更新和折叠中断的实际 RAF 间隔、长任务、组件挂载耗时及图表生命周期。导航 0–220ms 与随后增强阶段分别采样；结果仅代表本地 CEF，不代表公网像素流帧率。

场景预设使用 `assets/presets` 中 480×270 WebP；用 `Scripts/ghs/build_ui_preset_thumbnails.py`（Pillow）可从四张完整 PNG 重建，不覆盖原图。

自动单元验证覆盖即时选中、连续重定向、重复激活、未变化的视口通知、减少动态偏好、追溯取消离开和完整页面状态机。上述时长是界面动画参数，不代表像素流的往返时延；服务器帧率和网络传输需分别测量。

React Bits 原组件及许可证保存在 `src/react-bits/`，第三方许可证会随离线包输出。组件来源：https://github.com/DavidHDev/react-bits/blob/main/src/content/TextAnimations/CountUp/CountUp.jsx 。
