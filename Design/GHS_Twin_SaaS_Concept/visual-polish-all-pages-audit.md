# 全页面视觉审查 · 2026-10-23

范围为全部 45 张画板和 42 个可复用组件，涵盖总览、库存、订单、设备、告警、追溯、场景、详情、空态、筛选、提示浮层、像素流后台及登录。每页均完成组件展开后的结构检查并重新导出；主要页面、详情与边界状态另行截图目检。

统一灰白表面 #F4F6F9、辅助文字 #536478、交互蓝 #356BFA；禁用文字 #6B7788，待处理图形 #D1843C / 文字 #976025，异常图形 #C85852 / 文字 #A84540。白色表单、卡片和浮层作为承载面保留。后台与登录只调整样式，确认、停止、重连和错误处理行为不变。

45 张导出尺寸均与源画板一致；当前缺失组件引用、可见布局越界、placeholder 均为 0。21 处新增信息提示承载单位、真实来源时间及数据口径；仍需展示的数据未核验标记保留。确认与停止等影响用户决策的操作提示保持可见。

| 画板 | 文字节点 | 信息提示 | 未核验标记 | 检查 |
| --- | ---: | ---: | ---: | --- |
| [00 · POI 与 HUD 设计系统](exports/current/bi8Au.png) | 78 | 0 | 0 | 结构与导出通过 |
| [01 · 内部总览 / 仓库空间态势](exports/current/CLx7Q.png) | 88 | 5 | 4 | 结构与导出通过 |
| [02 · 点位选中 / AGV 设备详情](exports/current/mP7E5.png) | 57 | 1 | 1 | 结构与导出通过 |
| [03 · 聚合展开 / 成员分页与定位](exports/current/d7P3z.png) | 110 | 5 | 4 | 结构与导出通过 |
| [04 · 告警定位 / AGV 低电量](exports/current/Wt7Vo.png) | 53 | 1 | 2 | 结构与导出通过 |
| [05 · 历史追溯 / 时间与事件联动](exports/current/iiFrY.png) | 58 | 0 | 3 | 结构与导出通过 |
| [06 · 库位 POI / 原设计与未核验标记](exports/current/gW9oH.png) | 116 | 5 | 4 | 结构与导出通过 |
| [07 · HUD 详情组件 / 车辆与设施](exports/current/UbszE.png) | 83 | 4 | 4 | 结构与导出通过 |
| [08 · 搜索与数据状态 / 边界反馈](exports/current/PE2am.png) | 34 | 0 | 5 | 结构与导出通过 |
| [09 · 交互路径 / 密度与动效规范](exports/current/r5SOcd.png) | 41 | 0 | 1 | 结构与导出通过 |
| [10 · 聚合预警 / 从异常到设备](exports/current/XJoOQ.png) | 98 | 5 | 4 | 结构与导出通过 |
| [11 · 库存 / 数量与货位分布](exports/current/F8Cox.png) | 112 | 4 | 4 | 结构与导出通过 |
| [17 · 库存明细 / 物料与货位详情](exports/current/XhUtw.png) | 66 | 2 | 3 | 结构与导出通过 |
| [12 · 订单 / 今日出入库作业](exports/current/lvDfx.png) | 81 | 0 | 2 | 结构与导出通过 |
| [18 · 订单详情 / 拣货与设备联动](exports/current/t4mlxm.png) | 63 | 0 | 2 | 结构与导出通过 |
| [13 · 设备 / 真实台账与场景映射边界](exports/current/zyWMm.png) | 77 | 3 | 2 | 结构与导出通过 |
| [14 · 告警 / 分级队列与处理状态](exports/current/lCf0H.png) | 78 | 1 | 2 | 结构与导出通过 |
| [15 · 追溯 / 物料批次与作业事件](exports/current/OA1Bd.png) | 72 | 1 | 2 | 结构与导出通过 |
| [16 · 场景 / 即时图层与库容设置](exports/current/kvTdT.png) | 63 | 1 | 1 | 结构与导出通过 |
| [19 · 订单 / 入库切换状态](exports/current/qNsRa.png) | 77 | 0 | 2 | 结构与导出通过 |
| [20 · 设备 / 充电设施切换状态](exports/current/ibTva.png) | 63 | 1 | 2 | 结构与导出通过 |
| [21 · 导航内容地图 / 七个业务入口](exports/current/RXvoP.png) | 60 | 0 | 3 | 结构与导出通过 |
| [22 · 业务状态 / 空值权限与确认反馈](exports/current/G316Rk.png) | 27 | 0 | 0 | 结构与导出通过 |
| [23 · 设备搜索 / 匹配结果与定位](exports/current/t1QfTH.png) | 99 | 5 | 4 | 结构与导出通过 |
| [24 · 仓库切换 / 当前与接入边界](exports/current/Lxvbj.png) | 91 | 5 | 4 | 结构与导出通过 |
| [25 · 像素流服务启动器 / 待启动](exports/current/RyNRe.png) | 36 | 0 | 0 | 结构与导出通过 |
| [26 · 像素流服务启动器 / 运行中](exports/current/ApVA8.png) | 47 | 0 | 0 | 结构与导出通过 |
| [28 · 像素流访问 / 自动连接进度](exports/current/tWZ13.png) | 18 | 0 | 0 | 结构与导出通过 |
| [27 · 启动器 / 配置与异常状态](exports/current/A5t3VD.png) | 43 | 0 | 0 | 结构与导出通过 |
| [29 · 像素流访问 / 连接边界反馈](exports/current/jCHwc.png) | 26 | 0 | 0 | 结构与导出通过 |
| [30 · 搜索与选中 / 中文输入和控件规范](exports/current/k2v5GZ.png) | 46 | 0 | 0 | 结构与导出通过 |
| [33 · 主仓库 POI / 当前交互规范](exports/current/M0wx5h.png) | 41 | 0 | 0 | 结构与导出通过 |
| [31 · 园区默认 / 唯一主仓库 POI](exports/current/cgOha.png) | 68 | 5 | 3 | 结构与导出通过 |
| [32 · 点击开顶 / 0.5 秒溶解流程](exports/current/q2RKW8.png) | 23 | 0 | 0 | 结构与导出通过 |
| [34 · 场景设置 / 即时控制与库容状态](exports/current/mG0YD.png) | 89 | 2 | 0 | 结构与导出通过 |
| [35 · 像素流后台 / 运行中](exports/current/uR0QK.png) | 88 | 0 | 0 | 结构与导出通过 |
| [36 · 像素流后台 / 已停止](exports/current/ieg9r.png) | 40 | 0 | 0 | 结构与导出通过 |
| [37 · 像素流后台 / 结束用户连接](exports/current/D6HC9.png) | 98 | 0 | 0 | 结构与导出通过 |
| [38 · 像素流后台 / 停止服务确认](exports/current/Jsit1.png) | 98 | 0 | 0 | 结构与导出通过 |
| [39 · 像素流后台 / 状态与参数反馈](exports/current/i8fzG.png) | 66 | 0 | 0 | 结构与导出通过 |
| [40 · 像素流访问 / 管理员结束连接](exports/current/tYSnE.png) | 14 | 0 | 0 | 结构与导出通过 |
| [41 · 像素流访问 / 服务已暂停](exports/current/aIei1.png) | 14 | 0 | 0 | 结构与导出通过 |
| [42 · 像素流后台 / 管理员登录](exports/current/jRpYB.png) | 16 | 0 | 0 | 结构与导出通过 |
| [43 · 像素流后台 / 登录失败](exports/current/F554L.png) | 17 | 0 | 0 | 结构与导出通过 |
| [44 · 园区总览 / 库容说明展开](exports/current/OiC8B.png) | 70 | 5 | 4 | 结构与导出通过 |

源稿原生保存状态与哈希以 [完整验证记录](visual-polish-all-pages-verification.json) 为准。源稿完整 API 恢复快照为 visual-polish-all-pages-canvas-recovery.json。浏览器与 UE 的运行行为由主任务独立验收。

最终运行图同步：56 处图片引用全部采用最新地图的 11 类真实截图；97 条场景锚点和选择框调整记录（88 个节点）已单独记录。45 张画板逐页截图检查，45 张当前 PNG 尺寸检查通过，已批准的最终修改包括 AGV 角框、两页提示底板、选择器区域文案及主仓“点击查看”；除此之外 UI 指纹一致。最终原生保存与哈希见验证记录。见 [最新场景验证](latest-scene-verification.json)。
