# UE 业务页面动效卡顿修复验收

## 问题与修改

原生 CEF 已使用 60 FPS 目标，普通导航选中状态也在发送 UE 命令前同步更新。瓶颈位于切页淡出结束后的同步组件重建：首次设备页 `afterPaint` 占用 63.695ms，与高光位移动画重叠；跨页数字从 0 重播，图表重复创建。场景预设缩略图还直接使用总计 11.43MB 的四张完整 PNG。

- 缓存最近 8 个视图的图表及数字，返回时复用；离屏停止动画和尺寸观察，淘汰时释放资源。
- 初次指标直接呈现实际值；真实数值变化才创建 React Bits 组件，从当前值进行 240ms 过渡，一次刷新集中提交。
- 字体就绪、首屏遮罩尚未揭开时，准备并缓存实际台账图表，首次进入设备页直接复用。其他冷图表在切页完成后每帧增强一个，准备期间保留完整静态 SVG/HTML。
- 图表更新保留 240ms 插值。收敛不再重复全量 `setOption`；尺寸变化时重新布局，柱图仅更新必要文字留白。
- 页面过渡与图表准备队列同步，快速导航取消旧目的地；修复切页中折叠导致队列暂停状态未释放的问题。
- 四张预设缩略图改为 480×270 WebP、异步解码，总计 155,132 字节；原 PNG 保留且哈希不变。

高光仍然只跟随已接受的点击或键盘激活，hover 不改变选中项。配色、布局、业务数据、场景和原生 C++ 均未修改。

## 本地实测

在相同项目地图、1920×1080、`-game -RenderOffscreen -TwinDiagnostics` 的独立 UE/CEF 进程测量。使用真实时间、60 FPS 目标，没有固定步长。未部署服务器。

| 场景 / 指标 | 基线 | 最终版本 |
| --- | ---: | ---: |
| 首次设备页，整段 RAF 最大间隔 | 66.664ms | 16.666ms |
| 首次设备页，同步 afterPaint | 63.695ms | 12.175ms |
| 首次设备页，新建图表 | 1 | 0 |
| 首次场景设置，整段 RAF 最大间隔 | 133.328ms | 16.666ms |
| 返回总览，同步 afterPaint | 17.815ms | 3.240ms |
| 45ms 连续导航，新建图表 | 5 | 0 |

最终 22 段性能场景未记录超过 50ms 的浏览器 LongTask；部分后续回访/模式切换仍有偶发 33.33ms RAF 间隔。隐藏面板时浏览器暂停产生的帧间隔不视为可见卡顿。RAF 时间戳、实际回调调度、系统鼠标输入和最终显示并非同一指标；这些结果不能外推为公网像素流帧率或所有机器恒定 60 FPS。

## 验证与证据

- Motion 单元/真实 ECharts SSR 测试：25/25。
- 页面业务、导航、追溯与布局回归：141/141。
- 独立真实 CEF 性能场景：22/22，包含首次/回访、45ms 连续导航、相同/变化快照及原生折叠中断恢复。
- 真实 CEF 功能验收：16/16，覆盖七页、图表复用、hover/click、折叠暂停和 390px 窄屏；11 张截图完成。
- 地图哈希未变，验收过程未保存资产；独立 QA 进程退出，用户编辑器保留。

本机证据位于：

- `Saved/UIMotion/performance_baseline_20261029_094904/performance.json`
- `Saved/UIMotion/performance_prepared_20261029_102425/performance.json`
- `Saved/UIMotion/performance-prepared-comparison.json`
- `Saved/UIMotion/20261029_102550/runtime.json` 及同目录截图

最终验收 SHA256：

- `app.js`: `87339156b1d108f71ea34f69101ab4c3621e457ecb39719a16d8338bbc968e87`
- `motion.js`: `bcd0eaa7eeaa50c0b0d44d911d179ae98b9f31d3259fc097c871f5c3486f87f6`

可重复验证脚本：`Scripts/ghs/verify_ui_motion_performance.py`、`Scripts/ghs/verify_ui_motion_runtime.py`。缩略图生成脚本：`Scripts/ghs/build_ui_preset_thumbnails.py`。
