# 2026-11-05 道路与铁路修订

适用关卡 `/Game/Maps/MPR_CAD_Warehouse_B50B57`。此目录是原 B50B57 来源的增量修订，不覆盖母体 blend、layout、manifest 或历史 ownership。

- `MPR_B50B57_TransportRevision.blend`：本次89个交通网格的 Blender 源。
- `manifest.json`：替换89个已有网格、移除29个旧网格的放置记录；其中一个道床对象已由用户删除，实际再移除28个。保留原资源文件供历史追溯。
- `layout.json`：保持其他轨道和道路拓扑，删除两条指定支线，局部修顺道路。
- `geometry_validation.json`：连续道床、统一枕木、地形净空及保护范围验证。
- `validation/index.json`：最终地图及89个UE资源SHA、原生FBX回读、UE重载、七个游戏视角和恢复证据。

构建依次运行 `build_mpr_transport_revision.py`、`validate_mpr_transport_revision.py`，然后在独立 Blender 进程运行 `export_mpr_transport_revision.py`；原生FBX分批回读入口为 `run_mpr_transport_blender_validation.py`。这些入口写独立修订目录，不重建主仓。

本次受控导入已完成。`apply_mpr_transport_revision.py` 的预检及一次性恢复入口绑定当前项目审计快照；不要在后续用户修改的关卡上直接重跑。后续修订需要新的用户状态快照和改动清单。现场 `Saved/MPR/cleanup_20261105/` 的完整备份和报告未纳入 Git，正式证据已压缩归档；重新构建验证环境时须按归档索引恢复对应输入，不把历史ownership改写成新状态。

UE5.8自动重导会优先使用资产保存的 FBX 导入选项。入口临时选择 legacy FBX，设置保存的顶点颜色策略、禁用自动碰撞和光照UV生成，结束后恢复工厂开关。最终89个资源的简单/凸包碰撞均为0。

视觉检查：近景的斜向道床裂缝不再出现；原300米密疏切换处采用连续2.25米枕木间距；两条西侧支线及独占道床区域移除。标注道路连接已圆滑衔接，CB1贴建筑保护轮廓处保留小范围避让。主楼及内部对象逐项一致。七张静态画面不等同于连续运动录像或像素流性能测试。
