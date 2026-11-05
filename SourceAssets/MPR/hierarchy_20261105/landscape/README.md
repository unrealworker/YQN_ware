# 主仓园区植被层级

直接作用于 `/Game/Maps/MPR_CAD_Warehouse_B50B57` 的既有关卡。

- 现有 1,282 棵树的位置、旋转、比例和 HISM 实例顺序全部保留。
- 根据当前场地多边形的凸包外扩 15 米，选中园区周围的 111 棵：78 棵园区行道树与 33 棵原 CAD 树。
- 11 个原 HISM 组件使用实例颜色掩码，其中未选中的实例继续使用原叶片颜色；其余组件完全不变。背景共 1,171 棵。
- 西侧补 14 棵，东侧补 6 棵。沿线间距 12 米，树冠半径 2.4 米，预留额外 0.25 米树冠余量；避开道路、铁路、水面和建筑外扩 0.35 米后的范围，以及全部既有硬质铺装和原树冠。
- 新树只新增一个 HISM 组；现有树不迁移，不重新生成。
- 园区草地只更换 `MPRSC_MPRR_CampusGreen` 组件的一个材质。周边 `MPR3_Grass` 和背景树材质资源不修改。

颜色是 sRGB：园区绿地 `#8EAA72`；树冠中间色 `#819965`、亮部 `#9AAF82`、暗部 `#687F53`。最终以固定相机、固定曝光的 UE 实拍确认。

## 调用

UE 编辑器中将 `Tools/MPRWarehouse` 放入 Python 路径后：

```python
import mpr_campus_hierarchy
result = mpr_campus_hierarchy.apply(unreal)
```

该模块只保存 `/Game/MPRWarehouse/Hierarchy/Materials` 中自有标记的新材质，不加载或保存地图。返回 `expected_changes`、`new_actors`、`new_actor_ids`，供统一场景保护检查和最终保存使用。重复调用复用自有资产和新增树组，不新增重复树；遇到未通过身份、材质或实例变换检查的对象会停止。

原叶材质父级被复制后，保留其法线、粗糙度等连接，只将 BaseColor 改为原 `Tint` 和 `CampusTint` 的混合；`PerInstanceCustomData[0]` 经 `VertexInterpolator` 的 `VS` 输入送入混合掩码。0 为原色，1 为园区树色。

## CPU 验证

生成脚本为 `Tools/MPRWarehouse/build_mpr_landscape_hierarchy.py`。它从当前保护快照匹配全部 1,282 棵原树，应用既有 39 棵行道树迁移记录，保存全部实例变换并验证 20 棵补植的几何安全边界。新增树高度直接采样既有地形 FBX，当前落地 Z 为 -1.19 米。

本目录记录的是准备数据，不能替代 UE 材质编译、场景保存后回读、固定机位截图和帧率验证。
