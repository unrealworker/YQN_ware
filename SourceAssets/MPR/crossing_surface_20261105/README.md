# F97 支线与 C08 道路交叉口修复

用户确认保留支线，只修复交叉口路面。目标为 `Crossing_04`，CAD 中心约 `(11.819585, -398.831691)` 米，轨道 F97 与道路 C08 夹角约 12.878°，原浅色道口因此呈现明显长白带。

在原 MPR 关卡内局部替换 8 个网格：道口及过渡面改用当前 C08 道路的有效材质，去除路幅内外露的道砟和枕木；钢轨网格、路径、高度均保留。没有删除或新增 Actor。相邻道口及范围外几何保持一致，钢轨顶面与道口最小净空约 8.23 毫米。

新资产只存放在 `/Game/MPRWarehouse/CrossingSurface20261105`，旧共享资产保留。`manifest.json` 明确列出 8 个旧/新包路径、材质槽映射及道路材质来源。

两块道口过渡面还作了局部平滑法线修正，并将同一道口边缘 115 个残留旧材质小面统一为 C08 沥青材质。FBX 顶点、面、UV、EdgeFade 颜色及非局部法线保持一致；精确修改范围见 `residual_material_validation.json`，法线验证见 `ramp_normals_validation.json`。源三角数为 108 / 1211，UE 构建后的有效三角数为 108 / 1199，分别记录于 `validation/normal_refinement.json`。微小三角和 float32 精度检查见 `native_degenerate_audit.json`，不以源面数直接代替运行时三角数。

最后沿该道口的实际坡面范围裁掉残留道砟，消除最高约 6.64 厘米的穿面；道路、坡面和钢轨高度不变。证据见 `residual_ballast_validation.json`。最终共有 8,642 个源三角；原阶段 5,517 个保留面中，5,447 个完整保留、50 个仅获局部材质/法线许可、20 个获局部道砟裁切许可。

6 项范围与裁剪回归检查、FBX 回读、同层其他几何保持检查、原生 UE 保存后独立重新加载均通过。固定相机的 1920×1080 对照为 `validation/before_crossing.png` 与 `validation/after_4.png`，总览及主仓细节见 `after_1..3.png`。原生帧时与GPU采样在 `validation/capture_report.json`，此为单机 `UnrealEditor -game -RenderOffscreen -MPRProfile` 静态总览的15秒采样，不代表完整业务交互或Pixel Streaming负载。

执行入口：`mpr_scene_patch_guard.run(unreal, 'crossing')`。应用函数 `mpr_crossing_surface.apply(unreal)` 本身不打开/保存地图；统一保护器仅在场景白名单、资产哈希核验通过后保存当前原地图。

本目录的 8 个 FBX 是最终导入源。`MPR_Crossing04_Surface.blend` 和 `geometry_payload.json.gz` 记录初始裁切阶段；后续法线、残留材质及道砟修正分别由 `approve_mpr_crossing_normals.py`、`finish_mpr_crossing_material.py`、`finish_mpr_crossing_ballast.py` 生成，并由最终验证器按明确许可核对。
