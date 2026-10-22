# 仓储数字孪生 · 当前设计入口

**唯一编辑源：[Saas.pen](Saas.pen)。00–30 号画板已于 2026-10-21 获准开发；2026-10-22 新增的 31–33 号主仓库 POI 为待确认提案，本轮仅设计，未修改 UE 或网页程序。**

Pencil 已打开项目内的主文件。原有页面和公共组件已直接覆盖更新，三张重复的旧圆角确认页已移除。保留白色平面底色、深蓝文字、蓝色交互与 12px 圆角，不使用渐变。当前共 34 张画板、41 个可复用组件；设备图片和业务图表保留。

## 主仓库 POI · 待确认提案

| 内容 | 预览 |
| --- | --- |
| 屋顶显示，默认唯一主仓库标签 | [园区默认](exports/current/cgOha.png) |
| 点击标签，展开查看内部入口 | [仓库选中](exports/current/q2RKW8.png) |
| 默认、悬停、展开及进出规则 | [状态与交互](exports/current/M0wx5h.png) |

详细规格：[warehouse-poi-design.md](warehouse-poi-design.md)。31–33 号在同一主文件内维护；没有另建同名候选稿。原 00–30 号维持既有批准状态；本次提案获准后，带屋顶的园区默认状态以 31 号为准，原设备总览用于内部状态。后续调整直接覆盖这三张画板及对应导出。

## 已批准设计预览

| 内容 | 预览 |
| --- | --- |
| 仓库总览与统一导航 | [总览](exports/current/CLx7Q.png) |
| 完整设备选中框与详情 | [设备详情](exports/current/mP7E5.png) |
| AGV 搜索结果与定位入口 | [搜索](exports/current/t1QfTH.png) |
| 当前 GHS 仓库与未来切换 | [仓库切换](exports/current/Lxvbj.png) |
| 像素流服务启动器 · 待启动 | [启动器](exports/current/RyNRe.png) |
| 像素流服务启动器 · 运行中 | [运行状态](exports/current/ApVA8.png) |
| 启动器配置、端口与异常状态 | [配置与异常](exports/current/A5t3VD.png) |
| 像素流自动连接进度 | [加载页](exports/current/tWZ13.png) |
| 连接超时、踢出与重连 | [连接状态](exports/current/jCHwc.png) |
| 中文输入、选中态与动效规范 | [交互规范](exports/current/k2v5GZ.png) |

完整机器可读索引：[current-design.json](current-design.json)。本轮评审：[taste-current-review.md](taste-current-review.md)。

## 本轮设计决定

1. 删除场景中的独立缩放/复位组件，把 +、− 放到右侧导航“全仓”上方；保留“全仓”恢复默认视角并清除选中。
2. 左上角改为当前仓库选择器，明确显示 GHS 和当前区域。当前只有 GHS，不提供虚构的已接入仓库。
3. 搜索限定当前仓库，支持设备名称、类型、编号和物料等。AGV 查询显示设备列表、位置、状态和定位入口；点击后平滑聚焦并打开详情。中文组合输入不触发未完成的查询，Enter 先确认候选；系统输入法候选窗仅作行为示意。
4. 类型筛选使用 3px 蓝色选中边框；模型使用 6px 蓝色四角框及白色衬边，覆盖完整模型。
5. POI 状态区高 24px，状态文字固定行高并垂直居中。
6. 启动器统一命名“像素流服务启动器”，设计程序路径、端口、窗口显示、分辨率、画质、共享/独立模式、自动资源分配及启动/运行/停止状态。关闭本地窗口仍需后台渲染；60 FPS 是上限，不是保证。运行中显示实际帧率和当前目标。
7. 加载页采用相同白底、深蓝顶栏和蓝色状态语言，展示实际连接阶段与等待时间；首帧就绪后自动进入，默认静音，不伪造完成百分比。
8. 搜索框与面板共同移动；页面切换、菜单、聚焦与全仓复位的状态联动以交互规范画板为准。

## 保留的业务内容

总览、库存、订单、设备、告警、追溯、场景七个业务入口，以及物料、订单、设备详情继续保留。业务说明与演示数据：[business-design-brief.md](business-design-brief.md)、[business-demo-data.json](business-demo-data.json)、[visual-demo-data.json](visual-demo-data.json)。

设备编号、库存数据、帧率、会话和地址在画板中是设计样例，不表示实时接口或实际运行状态。

## 全部画板

| 画板 | 尺寸 | 预览 |
| --- | --- | --- |
| 00 · POI 与 HUD 设计系统 | 3840 × 1080 | [打开](exports/current/bi8Au.png) |
| 01 · 总览 / 仓库空间态势 | 1920 × 1080 | [打开](exports/current/CLx7Q.png) |
| 02 · 点位选中 / AGV 设备详情 | 1920 × 1080 | [打开](exports/current/mP7E5.png) |
| 03 · 聚合展开 / 成员分页与定位 | 1920 × 1080 | [打开](exports/current/d7P3z.png) |
| 04 · 告警定位 / AGV 低电量 | 1920 × 1080 | [打开](exports/current/Wt7Vo.png) |
| 05 · 历史追溯 / 时间与事件联动 | 1920 × 1080 | [打开](exports/current/iiFrY.png) |
| 06 · 库位 POI / 悬停轻预览 | 1920 × 1080 | [打开](exports/current/gW9oH.png) |
| 07 · HUD 详情组件 / 车辆与设施 | 1920 × 1080 | [打开](exports/current/UbszE.png) |
| 08 · 搜索与数据状态 / 边界反馈 | 1920 × 1080 | [打开](exports/current/PE2am.png) |
| 09 · 交互路径 / 密度与动效规范 | 1920 × 1080 | [打开](exports/current/r5SOcd.png) |
| 10 · 聚合预警 / 从异常到设备 | 1920 × 1080 | [打开](exports/current/XJoOQ.png) |
| 11 · 库存 / 容量与货架货位 | 1920 × 1080 | [打开](exports/current/F8Cox.png) |
| 12 · 订单 / 今日出入库作业 | 1920 × 1080 | [打开](exports/current/lvDfx.png) |
| 13 · 设备 / 状态筛选与空间定位 | 1920 × 1080 | [打开](exports/current/zyWMm.png) |
| 14 · 告警 / 分级队列与处理状态 | 1920 × 1080 | [打开](exports/current/lCf0H.png) |
| 15 · 追溯 / 物料批次与作业事件 | 1920 × 1080 | [打开](exports/current/OA1Bd.png) |
| 16 · 场景 / 图层视角与显示设置 | 1920 × 1080 | [打开](exports/current/kvTdT.png) |
| 17 · 物料详情 / 货位批次与订单 | 1920 × 1080 | [打开](exports/current/XhUtw.png) |
| 18 · 订单详情 / 拣货与设备联动 | 1920 × 1080 | [打开](exports/current/t4mlxm.png) |
| 19 · 订单 / 入库切换状态 | 1920 × 1080 | [打开](exports/current/qNsRa.png) |
| 20 · 设备 / 充电设施切换状态 | 1920 × 1080 | [打开](exports/current/ibTva.png) |
| 21 · 导航内容地图 / 七个业务入口 | 1920 × 1080 | [打开](exports/current/RXvoP.png) |
| 22 · 业务状态 / 空值权限与确认反馈 | 1920 × 1080 | [打开](exports/current/G316Rk.png) |
| 23 · 设备搜索 / 匹配结果与定位 | 1920 × 1080 | [打开](exports/current/t1QfTH.png) |
| 24 · 仓库切换 / 当前与接入边界 | 1920 × 1080 | [打开](exports/current/Lxvbj.png) |
| 25 · 像素流服务启动器 / 待启动 | 1200 × 900 | [打开](exports/current/RyNRe.png) |
| 26 · 像素流服务启动器 / 运行中 | 1200 × 900 | [打开](exports/current/ApVA8.png) |
| 27 · 启动器 / 配置与异常状态 | 1920 × 1080 | [打开](exports/current/A5t3VD.png) |
| 28 · 像素流访问 / 自动连接进度 | 1440 × 900 | [打开](exports/current/tWZ13.png) |
| 29 · 像素流访问 / 连接边界反馈 | 1920 × 1080 | [打开](exports/current/jCHwc.png) |
| 30 · 搜索与选中 / 中文输入和控件规范 | 1920 × 1080 | [打开](exports/current/k2v5GZ.png) |
| 31 · 园区默认 / 唯一主仓库 POI 提案（待确认） | 1920 × 1080 | [打开](exports/current/cgOha.png) |
| 32 · 主仓库选中 / 查看内部提案（待确认） | 1920 × 1080 | [打开](exports/current/q2RKW8.png) |
| 33 · 主仓库 POI / 状态与交互提案（待确认） | 1920 × 1080 | [打开](exports/current/M0wx5h.png) |

## 交付边界与版本规则

已检查画布、全尺寸 PNG、共享组件、布局边界，并完成独立 taste 复核；静态设计无法验证中文输入法、UE 镜头、浏览器会话和响应式运行行为。

用户已于 2026-10-21 明确下达开发命令。对应实施及验收记录见 [开发计划](../../docs/superpowers/plans/2026-10-21-approved-hud-streaming-ui.md)。代码完成并验证后，按用户要求自动使用中文提交 Git，仅提交对应任务的修改。

旧导出已移至 [archive/superseded-exports](archive/superseded-exports/)，仅供历史追溯，不作为开发依据。历史评审不代表当前设计状态；出现冲突时，以本 README、Saas.pen、current-design.json 和 exports/current 为准。


