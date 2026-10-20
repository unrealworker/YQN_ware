# GHS Twin UI · taste-skill 运行态评审

日期：2026-10-20。对象：`Content/GHSTwinUI/web` 与 Unreal 实际嵌入的 CEF 面板。

依据：`C:/Users/28109/.agents/skills/design-taste-frontend/SKILL.md`、`references/app-screens.md`、`references/critique.md`。这是长期使用的仓储业务界面，采用 app-screen 规则。沿用已批准的 `Design/GHS_Twin_SaaS_Concept/exports/visual-v4` 白色面板、灰蓝文字、蓝色数据、模型图片和四张紧凑指标卡；不重新随机抽取风格。四张指标卡是用户参考和已批准设计的明确要求，无图标底板、无虚构同比。

## 评审证据

- [1920×1080 总览实际运行截图](../Saved/GHS_TwinUI_Full_Overview.png)
- [1920×1080 设备详情实际运行截图](../Saved/GHS_TwinUI_Full_Device.png)
- [CEF / 原生桥接运行记录](../Saved/GHS_TwinUI_Runtime_Full.json)
- [批准设计总览、七页与设备详情](../Design/GHS_Twin_SaaS_Concept/exports/visual-v4/sidebar-contents.png)

截图来自 Unreal `Shot showui`，包含当前三维场景、原生 HUD 和实际浏览器面板。不是静态 HTML 示意图。独立 taste inspector 的 Edge 启动失败，未将其声称为通过；本轮采用真实 CEF 的截图、页面报告和运行交互。

## ROUND 1

Seen in one second: 左侧为实际仓库，右侧总览的容量环图和订单比例提供第一判断；点击 AGV 后有该类型的模型大图。

Idea (one sentence): 用当前仓库的空间对象建立定位，用模型图片确认身份，用比例与趋势表达业务规模。

Live thing: 七页切换、对象选择、设备聚焦、搜索筛选、详情返回、图层设置已经有运行路径；设备不存在或遥测缺失时保留真实边界。

Layout words by section: 总览=双列指标/薄环/堆叠条/状态条；库存=空间矩阵；订单=趋势/队列；设备=模型图/状态/任务；场景=预设缩略图/图层。

Scores: design 7.6 · usability 7.4 · creativity 7.0 · content 8.0 → overall 7.5

Caps applied: 应用界面不使用营销页的“四张照片”和“最低动效”上限。此轮评分仅针对已观察的桌面运行截图，小屏未观察前不声称响应式已验证。

Top three problems (most visible first), each with the screenshot it shows in and the fix:

1. `GHS_TwinUI_Full_Device.png`：遥测未接入时，环图和右侧电量各放一个大破折号，重复占据注意力；同时“暂无任务”会把未知任务误写为空任务。已改为环图保留未知值，旁边显示“遥测未接入 / 场景位置仍可定位”，任务字段显示“未接入”。离线则显示“设备离线”。
2. 两张桌面截图：CEF 的中文正文细且接近宋体观感，和批准稿的无衬线层级存在距离。本机已确认微软雅黑字体存在，CSS 改为优先 `Microsoft YaHei UI / Microsoft YaHei`，保留项目 Droid 字体作为离线后备，不复制系统商业字体。
3. 三维区域的初始仓库右边被面板遮挡、搜索提示太淡、缩放减号显示异常，影响整体判断。这些是原生层问题，已交给原生集成修复；不通过压缩业务面板掩盖。

## 已确认的桌面质量

- 图形与数字同源：库容 1728 + 576 + 96 = 2400；入库 96/128=75.0%、出库 118/156=75.6%，每条以自身总量为 100%。
- 106 台作业设备与 56 个设施分开。原生设备快照优先；未接入在状态图中有独立一行，不能算成运行或画成零电量。
- 总览 1920×1080 的首屏可看到库存、订单、设备和待关注入口。主要内容共享左右边缘，无阴影卡片堆叠。
- AGV 图片主体完整，深灰模型背景与白色面板形成对象层级；图片注明“设备模型预览”，不冒充实物照片。
- 实际 CAD 物料选择显示 CAD ID、实例和层列；480 件的 SKU2038 单独标为演示，不能写到任意场景货位上。
- 运行记录中的七个页面均报告 `overflow=false`、`imageFailures=[]`。该检查针对水平边界和资源，不替代截图检查。

## ROUND 2

Seen in one second: 1366 宽设备页仍能识别 AGV 模型；600 竖向窗口保留上半部实时三维，下半部为业务面板。

Idea (one sentence): 以可读的文字尺寸和独立滚动面板适应分辨率，不整体缩小桌面设计。

Live thing: 1366×768 和 600×900 的原生 / CEF 验证均完成 14 项检查；每个宽度的七页切换、图片、实际 CAD 物料选择、图层与定位路径均通过。

Layout words by section: 桌面=场景/纵向导航/右栏；窄窗口=场景/底部业务面板；详情=模型图/数据状态/固定动作。

Scores: design 7.7 · usability 7.6 · creativity 7.0 · content 8.0 → overall 7.6

Caps applied: 首次 1366 检查发现原生 HUD 沿用了旧 DPI 缩放，已经修复并重新运行；旧截图不作为最终尺寸验收。此轮 600 的导航可达性问题仍需修复后复核。

Top three problems (most visible first), each with the screenshot it shows in and the fix:

1. `GHS_TwinUI_Portrait_Overview.png`（17:19 初检）：底部面板只有 468px 高，纵向导航出现滚动条，第七个“场景”入口需滚动。已增加 `width >= 450px / height <= 600px` 的独立布局，改为 54px 高的横向七导航，全部目的地同时可见。
2. `GHS_TwinUI_Small_Device.png`（17:14 初检）：设备定位和历史追溯落到首屏以下。已将设备动作固定在业务面板底部，滚动正文预留 92px，避免末尾数据被盖；17:18 重跑的小屏截图中两个动作始终可见。
3. 未接入状态的重复破折号与未知任务误写为空已修正。`GHS_TwinUI_Portrait_Device.png`（17:19）显示模型完整、明确“遥测未接入”，固定操作区报告 `detailActionsVisible=true`。短面板图片限制 150px 高并保持完整，不裁切设备。

证据：

- [1366×768 总览](../Saved/GHS_TwinUI_Small_Overview.png) · [设备详情](../Saved/GHS_TwinUI_Small_Device.png) · [实际物料](../Saved/GHS_TwinUI_Small_Material.png) · [运行报告](../Saved/GHS_TwinUI_Runtime_Small.json)
- [600×900 总览](../Saved/GHS_TwinUI_Portrait_Overview.png) · [设备详情](../Saved/GHS_TwinUI_Portrait_Device.png) · [实际物料](../Saved/GHS_TwinUI_Portrait_Material.png) · [运行报告](../Saved/GHS_TwinUI_Runtime_Portrait.json)

修复后的物理面板尺寸为：1920×1080 → 480×1016；1366×768 → 380×704；600×900 → 600×468。字体保持实际像素尺寸，内容在面板内滚动。

## ROUND 3

Seen in one second: 600 窗口的七个业务入口横向展开，设备模型完整可辨，定位和追溯动作固定在底部。

Idea (one sentence): 把可观察的三维场景与可操作的业务面板分开适配，让分辨率变化不影响识别和下一步操作。

Live thing: 17:23 的 Portrait 重跑完成 18 项检查，业务导航、设备模型、CAD 物料点击、图层和 CEF 连接均通过；设备动作区 `detailActionsVisible=true`。

Layout words by section: 600=三维观察区/横向业务导航/滚动内容/固定动作；1366=场景/52px导航/窄业务栏；1920=场景/56px导航/完整业务栏。

Scores: design 7.8 · usability 8.0 · creativity 7.0 · content 8.0 → overall 7.7

Caps applied: 评估范围是仓储应用，未使用营销页面图片数量规则。未将尚未接入的业务数据或设备遥测计作已完成的数据集成。

Top three problems (most visible first), each with the screenshot it shows in and the fix:

1. `GHS_TwinUI_Portrait_Overview.png`（17:23）：已确认七个导航同时可见，导航不再需要纵向滚动；正文保留独立滚动。
2. `GHS_TwinUI_Portrait_Device.png`（17:23）：设备模型完整，固定动作在 600×468 CEF 视口内；较长的状态、任务区域按设计在面板内部滚动，不压小字体。
3. `GHS_TwinUI_Portrait_Material.png`（17:23）：实际货架物料具有选中框，详情明确场景来源和 CAD 标识。无新增视觉阻断项。

独立代码评审另修正两条交互：显式再次选择同一个对象会重新打开详情，后台周期快照仍不会打断返回；全局搜索 SKU2038、物料名称、规格或批次进入明确标注的演示物料，A-03 进入演示矩阵，其余查询仍遵循真实设备快照。两条均增加先失败、修复后通过的回归用例。

## 数据与验证边界

实际编辑器补充复核：Windows 150% 缩放使 383px 物理侧栏对应约 255 CSS px。首次检查暴露七导航最小宽与内部地图名撑宽，已改为七等分导航、业务名称和长字段换行；总览、库存、订单、设备、告警、追溯、场景七页在最终嵌入 PIE 中均报告 `overflow=false`。设备操作的 DOMRect 为分数像素，诊断保留严格边界和原始矩形，仅可见性判断允许 1 CSS px 舍入误差。实际鼠标检查记录见 `Saved/GHS_TwinUI_ManualQA.json`，早期失败样本保留用于对照。

业务示例尚未连接 WMS，历史轨迹未接入时保留空态，不以演示线代替实际轨迹。设备模型图是对应类型的模型渲染，不是每个序列号的现场照片。图表、布局和模型图片已在实际 CEF 中观察，17 项 Node 测试覆盖数量关系、过滤、返回上下文、主动重选、桥接控制及高 DPI 诊断；截图和静态报告不能证明所有动画中间帧都无掉帧。

结论：批准的浅色 SaaS 视觉已在实际场景落地，图片与图表承担识别和判断；三种已检查尺寸没有报告水平溢出或图片加载失败。600 底部面板导航和关键设备操作已完成截图复核。

## 八项修订评审（2026-10-20，18:59 交付截图）

本轮延续 taste-skill 的 app-screen 规则，并以批准的 `visual-v4/00-poi-system.png` 为 POI 依据。判断重点是当前选中对象是否清楚、状态是否独立表达、常用动作是否可达、切换是否保持上下文。

- 42px 标签恢复对应类型线性图标、蓝底白字选中态、独立状态底色与引线锚点；4px 角框能清楚识别当前对象。已修正邻近充电设施标签覆盖选中 AGV 的问题。
- 第一轮实际区域截图发现避让后的引线和锚点穿过装卸车数量。已将所有引线放到卡片底层、连接最近边，并排除覆盖自身锚点的避让位置。18:59 的 `Revision8_Full_1920x1080_FloorPreset.png`、`RacksPreset.png` 独立复核均不再穿字。
- 1920/1366/600 三档七导航和设备底部动作均可见。600 窄场景使用更高的 AGV/设施俯视角，顶面基本可见；前缘仍可能被真实充电墙遮挡，不声称自动消除场景几何遮挡。
- 页面保留旧内容淡出后替换；真实 CEF 总览→库存记录 out/in/idle，约 320ms。周期快照不会打断阶段，快速切换以最后请求为准；详情退出会清空原生选择对应的详情栈，避免区域定位后仍显示旧设备。
- 货架/地堆预设使用实际区域图片和实例中心；区域 POI 与单个设备选择区分明确。货架钢结构不再制造无意义的选中对象，实际货物仍可进入 CAD 层列详情。

本轮评分：视觉 8.0、可用性 8.2、内容准确性 8.0。静态截图无新增视觉阻断项；自动化与运行记录见 `Saved/Automation/Revision8/index.json`（69 项）和 `Saved/Revision8_Full.json`（42 项），前端 27 项通过。截图不替代所有硬件上的帧率基准，真实鼠标短拖动的历史验证边界仍保留。
