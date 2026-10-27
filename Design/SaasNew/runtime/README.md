# 最新 UE 页面与场景设计资料

本目录用于迁移到 Figma 的素材准备。页面几何来自 UE 实际 CEF 页面，场景图来自独立 UE 游戏实例；本目录本身不是已完成的 Figma 文件。

- 来源提交：`73e7b58`。
- 地图：`/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`。
- 地图 SHA-256：`1a28e3301d524bbb9aa0a32556e684d1468d4c7f095544e8a3430599e5a5aa01`。
- 游戏截图尺寸：1920 × 1080；侧栏原生区域：x=1440、y=64、480 × 1016。
- 共 39 个可编辑 DOM 状态、40 张完整运行画面、30 张侧栏裁图、11 份原生 POI 几何、9 个页面本地图片资产。
- 原有地图、生产代码和用户打开的 Editor 均未修改；没有执行性能分析。

## 快速查看

- [七页总览](pages-contactsheet.png)
- [关键详情总览](details-contactsheet.png)
- [追溯状态总览](replay-contactsheet.png)
- [完整来源、相机与哈希清单](manifest.json)
- [DOM 层级与错误检查结果](validation.json)

## 场景底图

| 文件 | 内容 |
| --- | --- |
| `scene/campus-roof-closed.png` | 最新园区默认闭顶构图；隐藏 HUD 的真实场景截图 |
| `scene/warehouse-interior-overview.png` | 仓库屋顶展开后的内部全景 |
| `scene/replay-floor-overview.png` | 地堆追溯全景，测试回放 640 秒 |
| `scene/replay-forklift-trail-ring.png` | 人工叉车 02 载货运输近景，可见蓝色渐变长虚线及同色扩散底圈 |
| `scene/agv-cart-shell-close.png` | 最新蓝色 STEP 外壳，完整外轮廓；场景 ID 为 `GHN_FloorStacker_01`，实际网格 `SM_CartShell_1026`，19,965 三角面，38.2 × 50 × 19.55 cm |

`manifest.json` 中逐图记录相机位置、旋转、FOV、尺寸和 SHA-256。场景是位图素材，页面文字、按钮和图表另有原生几何数据。

## 页面与状态

七页主页面：`page-overview`、`page-inventory`、`page-orders`、`page-devices`、`page-alerts`、`page-trace`、`page-scene`。

关键详情：`devices-scene`、`detail-forklift`、`detail-agv`、`detail-stacker`、`detail-truck`、`detail-charger`、`detail-order`、`detail-alert`、`detail-material`。

追溯：`trace-orders`、`trace-paused`、`trace-follow`、`trace-follow-loaded`、`trace-events`、`trace-playing`、`trace-exit-dialog`。底部独立 CEF 时间轴另存 `trace-transport-paused`、`trace-transport-playing`。

各状态的 `dom/<名称>.json` 可转换为 Figma 可编辑节点；`screens/<名称>.png` 是完整运行截图，`sidebar/<名称>.png` 是对应侧栏对照图。时间轴没有单独侧栏截图。`trace-follow-loaded` 对应 640 秒载货运输，其他追溯状态主要对应 230 秒附近。

## DOM 转换约定

- `nodes[].id / parentId` 保留真实 DOM 层级；不含隐藏 Toast、隐藏弹窗、脚本或样式节点。只有 `trace-exit-dialog` 包含当时显式打开的确认弹窗。
- `bounds` 为 CEF CSS 像素坐标，原点是该 CEF 文档左上角。侧栏拼到完整 1920 × 1080 画板时，加 `nativePanel.x/y`。
- `nativePanel` 记录 CEF 原生容器位置、尺寸和 HUD 缩放。回放时间轴属于独立 CEF 文档，使用该文件自身的 `nativePanel`，不要套侧栏坐标。
- `style` 保留文字颜色、字体、字号、字重、行高、背景、边框、圆角、阴影、布局、SVG 填充和描边。CSS 字体依次为 Arial、Microsoft YaHei UI、Microsoft YaHei、GHSCJK；Figma 转换需按本机可用字体解析。
- `textRuns` 保留直接文本节点及其 Range 矩形、换行后的矩形。数字滚动内部结构已归一为最终业务数字，不会导入重复数字。
- 顶层 `svg` 字段为原始 SVG，包括 ECharts 图表、图标和 clipPath；建议作为矢量导入。不要同时把其内部文字重复创建。
- `image.src` 是原生产图片路径；`image.copiedAsset` 对应本目录 `assets/` 的离线文件。
- `dataset` 保留 `action`、`id`、`key`、`value` 等交互标签；`attributes` 保留 role、aria、标题、输入类型等。
- `input` 保留当前 value、checked、范围信息；伪元素的内容和样式另存 `pseudo`。
- 允许滚动区可视范围外的节点保留实际坐标，方便制作完整内容和 Figma 滚动区域；JSON 已排除 display:none / visibility:hidden / opacity:0，不应按视口截断删除所有下方内容。
- 原生 UE 顶栏、全局搜索和场景 POI 不属于这些侧栏 DOM。可从完整截图及生产源码重建，不要把它们误认为已包含在 JSON 中。

## 验证与边界

39 个 JSON 的节点 ID 唯一、parentId 引用完整；存在 Motion 诊断的页面均无错误，业务首帧为正式 CEF 尺寸。当前系统减少动态效果偏好为开启，本次静态素材采集保留该用户设置。页面包含的示例、未核验数据和标记均按生产页面保留。

采集脚本仅在 `Saved/FigmaRuntimeExport/` 下；运行实例使用 `-game -RenderOffscreen -TwinDiagnostics`，没有保存地图。实例 PID 22244、33404、43056、80116、83752、27784、35408、36348 均已退出，原用户 Editor PID 30652 保留。未修改生产代码，未执行 Git 提交。


## 补齐状态与配套图层（最后更新）

请优先使用 `board-state-mapping.json` 组装画板，避免把不同视角、时刻的 POI 或时间轴混用。追加状态见 `supplement-contactsheet.png`。补齐了订单入库、充电设施 tab、总览库容说明、追溯不足一小时校验、播放完成、手动结束确认、1440×900 跟随回放。

- `scene-crop/` 已按生产视图区裁好。1920×1080 源图裁 `(x=0,y=64,w=1440,h=1016)`；1440×900 源图裁 `(0,64,1060,836)`。放入同尺寸场景框可保持 1:1，不要将整屏截图直接 cover 到场景框。
- 所有普通场景采集只隐藏 HUD，侧栏布局和相机构图未折叠。例外是 `agv-cart-shell-close` 的独立产品相机：该图完整画面居中，使用整图 contain，不按侧栏裁图。详情见 `scene-crop-manifest.json`。
- `poi/` 来源为实际 `get_poi_report()`，包括完整屏幕坐标、anchor、状态、文字、颜色、尺寸及相机。转入 scene-crop 局部坐标时，y 减 64；如果放在整屏根 frame，保持原始坐标。
- 闭顶与内部全景、货架近景均有同名 POI 文件。货架近景当前实际 `labels:[]`，应移除旧设计上的物料标签，不应强行保留失效锚点。
- 回放 47 为 640 秒跟随叉车 02；48/50 为 230 秒自由视角；49/51 为 3600 秒完成；53 为 1440×900 下 640 秒跟随叉车 02。播放中画板 5 的独立场景取真实时刻 233.9687 秒，配套时间轴显示 `08:03:53`。
- 独立时间轴 CEF 的 backing viewport 大于实际剪裁范围。1920 时 `nativePanel=(24,888,1392,168)`，1440 时 `(24,708,1012,168)`；应按此容器放置并裁剪。时间轴可见根节点含 4px 外边距，不要误套侧栏位置。
- 旧 `trace-follow` 是 230 秒静止场景的历史导出，最新载货设计应使用 `trace-follow-loaded` 与 `trace-transport-loaded`。最新成对文件优先于此前未配对状态。

## 设备详情精确定位补采

板 2/23 使用 `scene-crop/detail-agv-current.png` 和 `poi/detail-agv-current.json`，实际选中 AGV-01，区域为“充电区”。板 4 使用 `scene-crop/detail-alert-current.png` 和 `poi/detail-alert-current.json`，实际选中 STACKER-04，区域为“地堆作业区”。原详情 DOM 保持不变。两个对应完整 UI 对照图为 `screens/detail-agv-focus-ui.png`、`screens/detail-alert-focus-ui.png`。

`search/current-search.json` 保存生产搜索接口返回的 AGV 查询、32 项真实搜索结果和前 8 行几何。搜索输入框为 `(1056,80,360,48)`，下拉框为 `(1056,136,360,584)`；下拉布局来自当前 `FGHSTwinSearchLayout` 与 `NativePaint` 的精确公式。此次查询使用现有 Pixel Streaming 输入接口，因此下拉由客户端绘制，原生截图中仅显示实际查询文本，不应声称下拉已经过原生截图验证。

补采实例 PID 18264 已退出，用户 Editor PID 30652 保持；地图 SHA-256 未变，未改生产文件、未做性能测试。见 `detail-alignment-validation.json`。
