# 地堆恢复、卷帘门编号和搜索框动画

目标地图：`/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`。

## 最终行为

- 地堆恢复原有全部 7,530 个实例（3726 Mid / 1904 Low / 1900 High），原变换、原网格、当前深蓝材质及 CAD 实例顺序保持。完整原元数据仍可直接匹配物料。
- 货架保持 1,629 个实例、25,056 个托位中 17,539 个占用（约 70%），只保留货架空缺。
- 87 扇卷帘门上方新增静态深蓝数字 1–87。自东墙北端向南，再沿南墙向西，按空间位置排序，不采用 CAD 门牌号码，也不使用可能乱序的 HISM 索引作为编号。
- 编号位于门上方居中，高度 500cm、字高 60cm。根据真实墙体几何求外墙面，再向外偏移 1.5cm 避免穿墙；正面朝建筑外侧。文字色为货架同色的线性顶点色 `(5,19,130)`。无碰撞、无 Tick。
- 搜索框使用面板每帧动画位置，与缩放/复位控件同步；搜索框右侧与面板保持 24px 间距。实际 UMG 输入区域随槽位置移动，不穿透触发场景选择或中键复位。窄屏底部抽屉模式维持顶部搜索稳定，动画末帧不改变显隐或宽度。
- 业务演示容量同步为货架 70%、地堆 100%、总体 80%（1920/2400，可用416，空位锁定64）。这些仍是标明的演示数据，不等同于模型几何托位计数。

## 验证

- UE 5.4.4 / MSVC 14.38 原生编译退出码 0：`Saved/DockNumbers/build.log`。
- GHS 自动化 84 成功、0 失败、0 警告：`Saved/DockNumbers/Automation/index.json`。
- 网页测试 51/51：`Saved/DockNumbers/web-tests.log`。
- 实际离屏 UE 在 1920×1080、600×900、900×700、960×768 下完成 30 项检查、16 段逐帧动画（收起、展开、中途反向）；搜索点击区域不穿透：`Saved/DockNumbers/search_runtime.json`。
- 新进程重新读取保存的地图，再在重启后的用户编辑器中复核：`Saved/DockNumbers/saved_verification.json`。335 个 Actor（原248 + 87门牌），地堆7530，货架17539/25056；所有原 HISM 变换逐项匹配，原 NormalWarehouse 地图和共享模型材质哈希不变。
- 已人工查看实际渲染的门牌1–3、58–60、85–87、满载地堆、货架空缺以及搜索框运动中间帧：`Saved/DockNumbers/*.png`。
- 已重新打开用户编辑器；视角恢复脚本记录：`Saved/DockNumbers/editor_restored.json`。本次未重新打包。

## 重现与记录

- `Scripts/ghs/apply_dock_numbers.py`：调用地堆恢复并添加/更新静态门牌，仅保存目标地图；从 `SourceAssets/GHS/ZcoolDockNumbers.json` 查看生成映射。
- `Scripts/ghs/restore_zcool_floor.py`：从原始成功建场记录恢复全量实例，不单独保存地图。
- `Scripts/ghs/verify_dock_saved.py`：在新 UE 进程中验证，避免 live bridge 持有 Python 对象引用时直接 LoadLevel。
- `Scripts/ghs/verify_search_motion.py`：实际 UMG 动画及输入验证。
- 编辑前地图备份：`Saved/DockNumbers/map_before.umap`。
- 初次验收曾在持有 Python 场景引用的 live bridge 中执行 LoadLevel，引发旧世界 GC 检查退出；地图此前已成功保存。已移除此重载方式，并以新进程完整验证确认保存结果。`apply_report.json` 保留早期失败记录，最终验收依据为 `saved_verification.json`，没有覆盖历史错误为成功。
- 旧 `apply_scene_refinements.py` 与 `check_scene_refinement_assets.py` 记录上一轮双区域70%方案；如需重跑应再执行本轮恢复，不能以旧脚本的地堆5271断言验收当前场景。
