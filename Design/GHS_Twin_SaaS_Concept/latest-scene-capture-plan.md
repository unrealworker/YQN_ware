# 最新地图图源替换清单

当前 Pencil 源稿共有 **56 个图片节点**，需要 **11 类最新实际地图截图**。包括开顶业务背景、闭顶园区、视角缩略和设备近景；组件引用会自动传播。全部图片已应用并原生保存，逐页导出已核对。

所有新图均来自最新 `/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`，建议 1920 × 1080，无 UI、无 POI、无选择框。室内必须使用对应开顶视角；单设备近景可保留真实周边环境。示例业务 ID 不作为实际 Actor 或台账绑定依据。

| 类别 | 图片节点数 | 对应画板 | 拍摄要求 |
| --- | ---: | --- | --- |
| 闭顶园区全景 | 15 | kvTdT、RyNRe、ApVA8、tWZ13、cgOha、uR0QK、ieg9r、D6HC9、Jsit1、tYSnE、aIei1、jRpYB、F554L、OiC8B | 默认园区闭顶全仓 |
| 开顶内部总览 | 11 | CLx7Q、d7P3z、iiFrY、XJoOQ、lvDfx、zyWMm、lCf0H、qNsRa、ibTva、t1QfTH、Lxvbj | 屋顶完全隐藏，保留完整内部布局与外墙轮廓，全仓居中 |
| AGV 与充电区环境 | 2 | mP7E5、Wt7Vo | 屋顶隐藏，充电站阵列和至少一台AGV可见，前景无墙遮挡 |
| 货架区域 | 6 | gW9oH、F8Cox、XhUtw、t4mlxm、OA1Bd、kvTdT | 屋顶隐藏，货架通道及货物细节清楚，原型标签空间预留 |
| 俯视视角 | 1 | kvTdT | 最新地图实际俯视预设，使用同轮24号纯场景截图 |
| 地堆区域 | 1 | kvTdT | 屋顶隐藏，地堆货物及通道清楚 |
| AGV 实景近景 | 3 | mP7E5、Wt7Vo、lCf0H | 当前地图真实AGV居中，完整可见，占画面约60–75% |
| 人工叉车实景近景 | 5 | UbszE、lCf0H、k2v5GZ | 当前地图人工叉车完整可见，保留货叉与驾驶员 |
| 电动堆高车实景近景 | 2 | UbszE、lCf0H | 当前地图电动堆高车完整可见 |
| 装卸挂车实景近景 | 4 | UbszE、lCf0H | 当前地图白蓝长挂车完整可见，不使用路面轿车代替 |
| 充电设施实景近景 | 6 | Wt7Vo、UbszE、ibTva | 当前地图充电箱、线缆与站位完整可见 |

准确节点、旧路径、最终文件及角色映射见 [机器可读计划](latest-scene-capture-plan.json)，文件哈希和实际 Actor 身份见 [图源记录](latest-scene-assets.json)。八类截图保留自完整纯场景采图，货架、地堆与 AGV 三类采用最后补拍；来源清单已复制保存，后续运行验收覆盖临时目录不影响设计图源。
