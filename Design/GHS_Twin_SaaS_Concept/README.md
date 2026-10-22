# 仓储数字孪生 · 当前设计入口

**唯一编辑源：[Saas.pen](Saas.pen)。00–34 号已获准开发。2026-10-23 最新修订：场景设置改为四图层即时控制，增加货架 80% / 地堆 100% 的视觉库容滑条及状态规范。已核验库存、设备台账和标有“数据未核验”的原业务设计均保留。**

Pencil 当前画布共 35 张画板、42 个可复用组件；`exports/current` 有 35 张 PNG。本次更新 16、21、32、33 号并新增 34 号，其余 30 张原画板的结构指纹保持一致。保留白色底、深蓝文字和工业蓝交互。**本次画布与导出已验证，Windows 锁屏阻止原生保存，`Saas.pen` 待解锁后由主任务保存确认；不能将导出成功视为源文件已保存。** 验证记录见 [scene-controls-verification.json](scene-controls-verification.json)。

未保存画布已通过 Pencil 读取 API 备份至 [scene-controls-canvas-recovery.json](scene-controls-canvas-recovery.json)，包含本次组件、五张相关画板及六个依赖组件。这是结构化恢复备份，不是 `.pen` 替代文件；恢复时需用 Pencil API 核对或重建节点并处理引用 ID，完成后仍须原生保存。

## 场景图层与库容 · 当前规范

四项为“建筑外壳”“货架与货物”“作业设备”“POI 标签”，开启色 `#356BFA`，关闭色 `#D8E0EC`，白色滑块。所有开关和滑条即时生效，删除“应用到当前视图”。货架默认 80%、地堆默认 100%，范围 0–100%，步长 1%；明确说明“仅调整场景货物展示，不改变实际库存。”隐藏货物图层后滑条禁用并保留数值。

闭顶和 0.5 秒开顶期间锁定内部标签与拾取，调整比例不自动开顶，提供“打开屋顶查看”。“全仓”恢复建筑、屋顶和园区视角，保留其他图层与比例；“恢复默认”恢复四层开启、标准密度、80% / 100%，保留当前相机与屋顶状态。快速反向操作以最后一次为准。详见 [正式控件规范](scene-controls-design.md)。

| 内容 | 预览 |
| --- | --- |
| 16号场景设置与闭顶场景 | [场景设置](exports/current/kvTdT.png) |
| 34号默认、隐藏货物和交互规则 | [状态规范](exports/current/mG0YD.png) |
| 默认面板近图 | [80% / 100%](exports/scene-controls-20261023/G81ak.png) |
| 货物隐藏后禁用滑条 | [保留数值](exports/scene-controls-20261023/QKnV0.png) |

## 已确认业务数据 · 当前规范

库存现存 **337,783**、可用 **336,006**、冻结 **55**、分配 **1,722**、待移出 **0**；数量单位待确认。156 货主、14,373 SKU、76,752 明细和 10 个区域主数据来自已核验查询，不推定真实容量、空位或占用率。设备台账 **82 条**，正常 **62**、维修中 **0**、禁用 **20**，是管理状态；实时在线与遥测暂无。

库存查询时间 `2026-10-22 22:27（UTC+08:00）` 与最大 ETL `22:01:21` 分开显示；当地时钟不表示数据更新时间。真实台账与场景模型分开，完整清单和位置映射待补。原库容 1,920/2,400 托位、80% 饼图及 48 格货位分布保留为“数据未核验”示例，和已核验数量分区展示；订单、告警、轨迹与充电设施同样标注未核验。详情、来源单元格、组件 ID 和限制见 [business-data-confirmed-design.md](business-data-confirmed-design.md)。

## 仓库地址与当地时钟 · 当前规范

顶部深蓝栏左中部显示两行地址：`17335 Glen Helen Pkwy`、`San Bernardino, CA 92407 美国`。右侧显示“仓库当地时间”和 `HH:mm:ss`，下一行显示 `YYYY.MM.DD · PDT (UTC−07:00)`；冬季自动切换为 `PST (UTC−08:00)`。

运行使用 `America/Los_Angeles`，每秒更新时间和日期。画板中的 `2026.10.22 / 07:38:00` 是静态设计样例，不表示当前时间或业务数据刷新时间。统一组件为地址 `yCuML`、时钟 `uzdua`，已应用于全部 20 张场景画板。详细规格与检查结果见 [warehouse-address-clock-design.md](warehouse-address-clock-design.md)。

## 主仓库 POI · 当前规范

| 内容 | 预览 |
| --- | --- |
| 屋顶显示，默认唯一主仓库标签 | [园区默认](exports/current/cgOha.png) |
| 点击即开顶，0.5 秒中心向两侧溶解 | [开顶时序](exports/current/q2RKW8.png) |
| 默认、悬停、开顶及复位规则 | [状态与交互](exports/current/M0wx5h.png) |

详细规格：[warehouse-poi-design.md](warehouse-poi-design.md)。31–33 号在同一主文件内覆盖维护。默认带屋顶状态以 31 号为准，01 号用于内部总览。全仓、中键和 Home 恢复外壳、屋顶及园区视角并取消待执行定位，保留其余图层偏好和库容；页面设备定位显示对应图层，先开顶再聚焦。主仓 POI 仅在外壳可见、屋顶闭合且 POI 开启时显示。旧二次确认展开卡片已移除。

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

完整机器可读索引：[current-design.json](current-design.json)。本轮业务数据规范：[business-data-confirmed-design.md](business-data-confirmed-design.md)。[taste-current-review.md](taste-current-review.md) 为此前视觉评审，不覆盖本轮数据口径。

## 本轮设计决定

1. 删除场景中的独立缩放/复位组件，把 +、− 放到右侧导航“全仓”上方；保留“全仓”恢复屋顶、默认园区视角并清除选中和待执行定位。
2. 左上角仓库选择器显示 GHS 和当前区域，删除“普通仓库”及其分隔符；顶栏显示“三维运营中心”。下拉选项使用单行“GHS · 当前仓库”，选项高 48px、下拉面板高 176px。当前只有 GHS，不提供虚构的已接入仓库。
3. 搜索限定当前仓库，支持设备名称、类型、编号和物料等。AGV 查询显示设备列表、位置、状态和定位入口；点击后平滑聚焦并打开详情。中文组合输入不触发未完成的查询，Enter 先确认候选；系统输入法候选窗仅作行为示意。
4. 类型筛选使用 3px 蓝色选中边框；模型使用 6px 蓝色四角框及白色衬边，覆盖完整模型。
5. 设备 POI 状态区高 24px，状态文字固定行高并垂直居中。主仓库 POI 保留“GHS · 主仓库”与“点击查看”、引线和屋顶锚点；默认、悬停及点击行为保持一致，不再显示“普通仓库”。
6. 启动器统一命名“像素流服务启动器”，设计程序路径、端口、窗口显示、分辨率、画质、共享/独立模式、自动资源分配及启动/运行/停止状态。关闭本地窗口仍需后台渲染；60 FPS 是上限，不是保证。运行中显示实际帧率和当前目标。
7. 加载页采用相同白底、深蓝顶栏和蓝色状态语言，展示实际连接阶段与等待时间；首帧就绪后自动进入，默认静音，不伪造完成百分比。
8. 搜索框与面板共同移动；页面切换、菜单、聚焦与全仓复位的状态联动以交互规范画板为准。
9. 所有场景顶栏沿用 64px 高度与 `#172333` 深蓝底，地址两行靠左中部、当地时钟靠右；面板展开或收起均保留地址和时钟。当地时间按仓库时区计算，不使用访问者本机时区。
10. 场景控制只影响当前会话；视觉库容与真实库存、未核验业务库容饼图相互独立。四开关、滑条、开顶、定位和两种复位边界以 [scene-controls-design.md](scene-controls-design.md) 为准。

## 保留的业务内容

总览、库存、订单、设备、告警、追溯、场景七个业务入口，以及物料、订单、设备详情继续保留。当前业务说明：[business-design-brief.md](business-design-brief.md)。[business-demo-data.json](business-demo-data.json) 与 [visual-demo-data.json](visual-demo-data.json) 是历史交互演示数据，不再作为真实库存或设备台账口径。

已核验库存和叉车台账是静态查询结果；场景模型编号、演示订单/告警、帧率、会话、服务访问地址和时钟时刻是设计样例，不表示实时接口或实际运行状态。顶栏仓库物理地址沿用已批准的固定展示文案。

## 全部画板

| 画板 | 尺寸 | 预览 |
| --- | --- | --- |
| 00 · POI 与 HUD 设计系统 | 3840 × 1080 | [打开](exports/current/bi8Au.png) |
| 01 · 内部总览 / 仓库空间态势 | 1920 × 1080 | [打开](exports/current/CLx7Q.png) |
| 02 · 点位选中 / AGV 设备详情 | 1920 × 1080 | [打开](exports/current/mP7E5.png) |
| 03 · 聚合展开 / 成员分页与定位 | 1920 × 1080 | [打开](exports/current/d7P3z.png) |
| 04 · 告警定位 / AGV 低电量 | 1920 × 1080 | [打开](exports/current/Wt7Vo.png) |
| 05 · 历史追溯 / 时间与事件联动 | 1920 × 1080 | [打开](exports/current/iiFrY.png) |
| 06 · 库位 POI / 场景映射待确认 | 1920 × 1080 | [打开](exports/current/gW9oH.png) |
| 07 · HUD 详情组件 / 车辆与设施 | 1920 × 1080 | [打开](exports/current/UbszE.png) |
| 08 · 搜索与数据状态 / 边界反馈 | 1920 × 1080 | [打开](exports/current/PE2am.png) |
| 09 · 交互路径 / 密度与动效规范 | 1920 × 1080 | [打开](exports/current/r5SOcd.png) |
| 10 · 聚合预警 / 从异常到设备 | 1920 × 1080 | [打开](exports/current/XJoOQ.png) |
| 11 · 库存 / 已核验汇总与区域主数据 | 1920 × 1080 | [打开](exports/current/F8Cox.png) |
| 12 · 订单 / 今日出入库作业 | 1920 × 1080 | [打开](exports/current/lvDfx.png) |
| 13 · 设备 / 真实台账与场景映射边界 | 1920 × 1080 | [打开](exports/current/zyWMm.png) |
| 14 · 告警 / 分级队列与处理状态 | 1920 × 1080 | [打开](exports/current/lCf0H.png) |
| 15 · 追溯 / 物料批次与作业事件 | 1920 × 1080 | [打开](exports/current/OA1Bd.png) |
| 16 · 场景 / 即时图层与库容设置 | 1920 × 1080 | [打开](exports/current/kvTdT.png) |
| 17 · 库存样例 / 物料与货位待关联 | 1920 × 1080 | [打开](exports/current/XhUtw.png) |
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
| 31 · 园区默认 / 唯一主仓库 POI | 1920 × 1080 | [打开](exports/current/cgOha.png) |
| 32 · 点击开顶 / 0.5 秒溶解流程 | 1920 × 1080 | [打开](exports/current/q2RKW8.png) |
| 33 · 主仓库 POI / 当前交互规范 | 1920 × 1080 | [打开](exports/current/M0wx5h.png) |
| 34 · 场景设置 / 即时控制与库容状态 | 1920 × 1200 | [打开](exports/current/mG0YD.png) |

## 交付边界与版本规则

此前版本已完成独立 taste 复核。本次场景控制已检查画布、全尺寸面板 PNG、组件引用与源坐标边界；源文件落盘待主任务确认。静态设计无法验证中文输入法、UE 镜头、浏览器会话和响应式运行行为。本轮开发计划见 [场景控制实施计划](../../docs/superpowers/plans/2026-10-23-scene-controls.md)。

用户已于 2026-10-21 明确下达开发命令。对应实施及验收记录见 [开发计划](../../docs/superpowers/plans/2026-10-21-approved-hud-streaming-ui.md)。代码完成并验证后，按用户要求自动使用中文提交 Git，仅提交对应任务的修改。

旧导出已移至 [archive/superseded-exports](archive/superseded-exports/)，仅供历史追溯，不作为开发依据。历史评审不代表当前设计状态；出现冲突时，以本 README、Saas.pen、current-design.json 和 exports/current 为准。


