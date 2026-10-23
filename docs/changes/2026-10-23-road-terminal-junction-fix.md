# 道路末端渐隐与 Sycamore 交叉口修复

已保存到 `/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`。

## 原因与修改

- 当前关卡缺少 `GHSContextTransition_ContextRoads/Curbs/Markings` 三个 Actor，交通路线仍经过原 65 米延伸段，导致车辆出现在裸地上。恢复三个对象，复用原延伸模型的渐隐顶点色。
- 延伸材质起始色读取当前道路/路缘/标线材质，终端色复制当前地面的空间着色图。新增独立材质，没有修改用户的地面材质或变换。
- Sycamore 的两个路线端点同属内部四岔口，却生成了两条直线延伸。按原始面的精确坐标删除这两段的路面、路缘、标线及绿带，保留 Glen 两端和 I-15 四端。
- 生成器增加内部共享 CAD 接点判断，防止再次生成这两条错误延伸。交通路线 JSON 和车流代码未改变。

## 验证

- 4 项端点测试及 3 项现有交通路线测试通过；源模型组合校验通过。
- 14 个受保护源文件哈希相同；保留面的坐标和 EdgeFade 顶点色逐面一致，6 个绿岛和 35 棵外围树未重排。
- 原 367 个 Actor 中只有 `GHSContextTransition_Landscape` 的网格引用发生预期变更；增加上述 3 个 Actor 后共 370 个。全部原有变换和材质绑定保持一致。
- 独立 UE 运行实例从磁盘读取最终地图，确认 4 个修复网格可见，检查六个外侧端点及交叉口的截图。车辆完成回收与重新入场，固定 32 个实例、4 个组件，Actor 数量没有增长。
- 最终地图 SHA256：`437b8ffea48269c1a03da02901ea7f704e8187afe635a284da2bc184ffc9ab95`。编辑器无未保存地图或内容包。

验收记录与截图：`Saved/RoadTerminalFade/Runtime/verification.json`、`Saved/RoadTerminalFade/Runtime/*.png`。
修复前地图备份：`Saved/RoadTerminalFade/before-20261023-181739.umap`。
几何修改清单：`SourceAssets/GHS/RoadTerminalFade/road_terminal_junction_fix.json`。

本次更新 UE 项目与生成脚本；没有重新打包 Windows 发行包，也没有替换或开发追溯功能。
