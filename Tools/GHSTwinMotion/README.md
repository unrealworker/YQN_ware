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

- 导航选中高光 250ms，仅点击或键盘激活切换页面后移动。悬停显示按钮自身的淡蓝反馈，聚焦显示原有焦点框，不移动选中高光。
- 语义指标数字 680ms 从当前值过渡至新值，保留逗号、负数和小数。编号、时间、样例明细和未知值保持原文。
- 环图展开 600ms，柱条生长 450ms，趋势描画 650ms；数据更新 350ms。
- 页面内容 300ms 轻移淡入，相邻组错峰 35ms，上限 210ms；已有条目在遥测刷新时不重复入场。
- 同页刷新同步暂存并重新挂接原 React 根节点和 ECharts 实例。变化数据才调用 setOption，不变数据不重播。
- 面板隐藏、页面后台或减少动画偏好开启时立即收敛，清理动效。图表按真实布局尺寸响应，避免 UE CEF 百分比尺寸误读。
- 保留 SVG/HTML 静态回退和现有数据未核验提示，未接入任何新数据源。

## 验证

`Scripts/ghs/verify_ui_motion_runtime.py` 在单独的 `-game -RenderOffscreen -TwinDiagnostics` 进程验证真实 CEF，不修改或保存地图。截图和运行报告写入 `Saved/UIMotion/`。页面诊断在 `window.TwinMotion.diagnostics()`，原生报告包含 `motion` 字段。

React Bits 原组件及许可证保存在 `src/react-bits/`，第三方许可证会随离线包输出。组件来源：https://github.com/DavidHDev/react-bits/blob/main/src/content/TextAnimations/CountUp/CountUp.jsx 。
