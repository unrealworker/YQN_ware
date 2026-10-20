# V8 银蓝材质修订

2026-10-20。沿用已确认的空间控制台功能和信息密度，针对 V7 标题栏、面板接近白色而缺少材质层次的问题，增加明确的银蓝色表面与分区阅读层。仅修改 Pencil 设计，未开发网页或改动 UE。

## 表面与颜色

| 区域 | 设计处理 |
|---|---|
| 72px 主标题栏 | 两端 `#A9BFD0` → 过渡 `#CCDCE7` → 中央 `#E8F0F5` 的对称银蓝渐变；顶部细高光、底部细边与轻阴影；深蓝标题保持对比 |
| 44px 导航栏 | `#D4E0E9` 至 `#E5EDF3` 冷银底，当前模式 `#2B5D84` 配白文字/图标 |
| 384px 两侧面板 | 冷灰底座、银蓝标题与指标承托；按业务分区铺满，不新增外围留白 |
| 核心图表阅读层 | 乳白 `#F3F6F7`，承载吞吐折线、设备环形饼图、历史事件列表 |
| 次级比较层 | 冷灰 `#E6EDF2` / `#E5EDF2`，承载任务柱状图与月台作业 |
| 库容与连接底板 | 银蓝灰 `#CFDEE8` / `#C9D9E4`，建立页面底部承托 |
| 故障 / 预警 | 浅砖红 `#F1DDD8` 与浅赭 `#EFE6D3`；沿用文字、色条和图标，避免只靠颜色 |
| 场景工具栏 | 局部半透明冷银 `#D9E5EFF0`、16px 背景模糊效果与接触影；选中工具为实蓝 `#2B60A6` |
| 追溯时间轴 | 银蓝操作区 `#D4E2ED` 与乳白刻度区 `#F1F5F7`，回放与时间刻度分层 |
| 设备详情 | 银蓝设备身份区、乳白读数区、冷银动作区、浅赭全仓异常摘要 |
| 辅助小字 | 普通标签、单位和坐标轴加深为 `#455D6E`；标题栏辅助字 `#334F62`；小号正常 / 预警 / 故障分别使用 `#236355` / `#865A19` / `#963E36`，适配更深的表面底色 |

主视觉参考仍为 nvwa_futureDesign 的克制数据工作台与局部柔光面板。使用饱和色表达选择和状态，不为场景增加全屏蒙层。

## 六张画板

全部为 1920×1080，3D 底图铺满画布，网页层高于场景内 HUD。左右面板分别固定在 x=0 与 x=1536，宽 384px，自 y=116 延伸至底部；收起状态为两边 56px 工具轨。

| 画板 | Pencil ID | 导出 |
|---|---|---|
| 40 实时近景 | K20XOE | [40-live-closeup.png](exports/v8/40-live-closeup.png) |
| 41 实时全仓 | kMfWQ | [41-live-overview.png](exports/v8/41-live-overview.png) |
| 42 追溯近景 | RRB0l | [42-trace-closeup.png](exports/v8/42-trace-closeup.png) |
| 43 追溯全仓 | h8W2Pt | [43-trace-overview.png](exports/v8/43-trace-overview.png) |
| 44 设备详情 | GfCvE | [44-selected-device.png](exports/v8/44-selected-device.png) |
| 45 专注场景 | h5XEcs | [45-compact-scene.png](exports/v8/45-compact-scene.png) |

[修改前后对照](exports/v8/before-after.png) · [六屏总览](exports/v8/v8-comparison.png)

四张透明网页层：`exports/v8/overlay-live.png`、`overlay-trace.png`、`overlay-selected.png`、`overlay-compact.png`。半透明与背景模糊在实际网页中需要根据场景渲染方式接入；导出 PNG 不是运行时界面。

## 验证与范围

- 六张原尺寸页面均为 1920×1080；Pencil 六屏布局检查无越界或裁切问题。
- 四张透明层中心像素 alpha=0，两侧外沿 y=116–1079 的 alpha 均为255，确认中间透明且外沿没有漏缝。
- 复核实时近景、全仓、追溯与详情的材质区分、图表及文本可读性；保留 V7 历史设计便于比较。
- 示例数据、图表统计口径和功能流程沿用 [V7 说明](dashboard-v7-spatial-console-design.md)。全部数值为演示数据。
- 本轮为配色和表面材质修订；动效时序与桌面适配仍参考 V7 规范，未新增运行时动画、网页开发或手机稿。
