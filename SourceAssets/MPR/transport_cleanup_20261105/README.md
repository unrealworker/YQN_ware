# MPR 尾部交叉与残留白面修复

原关卡 `/Game/Maps/MPR_CAD_Warehouse_B50B57` 就地修改。尾部指定范围内的多余道路、铁路和道口删除；旧支线删除后遗留的两片白色道口面及坡面清除，补回道路、路缘和标线。

23 个局部交通网格替换、7 个空尾段 Actor 删除。其余 854 个 Actor、保留 Actor 的 GUID 和变换、树木实例、主仓及场地不变。新网格单独存放在 `TransportCleanup20261105`，原共享网格和材质不覆盖。第一轮修复不改变仍有效的 F97/C08 道口；该处按后续截图单独处理。

根因：旧生成器只用新网格 bounds 决定是否刷新；删除孤立部分后 bounds 缩小，遗留旧道口面。现同时检查旧、新 bounds。

验证：几何回填/残面检查、12 项生成和应用范围回归检查、23 FBX 回读；实际 UE 保存后在独立命令行进程重新加载。`validation` 包含完整场景保留记录和 1920×1080 同机位前后截图。`before_1/after_1` 为尾部，`before_2/after_2` 为用户指出的斜白面，第三组为发现的另一处同类遗留面。

入口：`Tools/MPRWarehouse/mpr_scene_patch_guard.py` 的 `run(unreal, 'transport')`；只操作当前原关卡，严格比较白名单后保存。局部源生成、导出、验证与应用代码同目录下以 `transport_cleanup` 命名。
