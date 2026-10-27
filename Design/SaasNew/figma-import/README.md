# SaasNew 本地原生迁移插件

该目录只生成 Figma 迁移包，不改 UE 项目、原 Saas.pen 或既有 Figma 文件。

## 构建

在 `D:\UEPro\Test` 执行：

```powershell
node Design/SaasNew/figma-import/build.cjs
node Design/SaasNew/figma-import/verify.cjs
node Design/SaasNew/figma-import/verify-visual.cjs
```

构建器优先读取 `Design/SaasNew/migration.pen.json`，不存在时回退到 `Design/GHS_Twin_SaaS_Concept/Saas.pen`。始终核验 54 画板、47 主组件。

`Design/SaasNew/runtime-overrides.json` 可提供：

```json
{
  "imageReplacements": {"images/old.png": "D:/UEPro/Test/Design/SaasNew/runtime/latest-scene.png"},
  "boardStatus": {"31": "已实现 · 最新 UE 实际页面"},
  "nodeIdMap": {"31:oldNodeId":"replacementNodeId"}
}
```

新增节点支持 frame/text/rectangle/ellipse/icon/path/ref，以及原生 SVG 的 `{ "type":"svg", "svg":"<svg...>" }`。未知类型/属性会停止导入，不会静默删除。所有图片离线嵌入；超过 4096 像素边长会拒绝构建，需先明确缩放。

`nodeIdMap` 允许替换运行时新节点的交互目标。若提供完整 `links` 数组，将替代默认的 `prototype-links.json`（条目字段为 sourceBoard/sourceNodeId/targetBoard/label/event）。

## 在 Figma 导入

1. 新建一个完全空白的 Figma Design 文件，命名为 **SaasNew**。
2. Figma 桌面端打开 Plugins → Development → Import plugin from manifest，选择本目录 `manifest.json`。
3. 若本地开发导入要求插件 ID，请先用 Figma 的 New plugin 创建一个本地插件，从 Figma 生成的 manifest 复制实际 ID，再执行 `node Design/SaasNew/figma-import/build.cjs --plugin-id <Figma分配的数字ID>` 后重新导入。不要编造远程插件 ID；后续构建会保留已分配 ID。
4. 运行插件，确认当前文件为新空白文件或本次可校验续传的文件后点击导入。插件将拒绝名称不匹配或存在无关内容的文件。异常时不会删除已有/已创建内容；保留错误输出进行检查。
   本次已记录的失败可续传：校验源哈希、既有 Figma 节点 ID、页面/模块结构和 sourceId 后逐层复用，不删除任何节点。未知内容仍拒绝；重复执行同一源不会创建副本。`resume-allowlist.json` 仅用于本次错误报告确认的文档，不是通用覆盖许可。
   已完成文件的视觉修订须匹配 `revision-allowlist.json` 固化的原 `339ca017…` 验收记录；旧源不再使用的节点只隐藏并清除交互，绝不移除。报告输出隐藏节点清单以及回读后的实际原型连接数。有效节点默认恢复可见，源画板名称与 `boardInteractions` 交互说明优先于旧 inventory。
5. 下载 `SaasNew-acceptance.json`，检查所有 `checks` 为 true、`errors` 为空；抽查中文字体、图片裁剪、54 画板导航及交互。
6. 点击 **导出视觉核验包**。插件用 Figma 官方 `node.exportAsync({format:'PNG',constraint:{type:'SCALE',value:0.5}})` 顺序导出全部 54 画板，不修改画板。完成后再手动点击 **下载视觉核验 ZIP**，不会自动下载。
7. ZIP 内有 `boards/` 下 54 张 PNG、`SaasNew-acceptance.json`、含节点 ID / CRC32 / 导出时间的 `visual-manifest.json`。若缺少画板或中途失败，不会提供不完整 ZIP，可修复后重新导出。ZIP 使用本地 STORE + CRC32，无额外权限或网络依赖。

## 组织与可编辑性

- “01 · 全流程原型”：全部 54 画板在同一页面内，按七个业务模块 Section 分区，保证原型能跨模块导航。
- “02 · 组件库”：原稿全部 47 个原生主组件。
- 最新 UE 页面组件通过 `runtimeComponentDefinitions` 另行追加，单独统计 `runtimeComponents`，不替代原稿 47 主组件，也不改变历史引用指向。
- “03 · 交互规范”：当前参数、功能状态和验收边界。
- 每个画板右侧有原生文字说明，明确页面交互与实现状态。后台页面标记“设计阶段”。
- 源稿的全部引用展开为可编辑图层（具体数量见 build-report / acceptance）；原组件 ID、覆盖内容、源节点 ID 保存在 pluginData。此策略确保结构性 overrides、图标替换和文字不会丢失，不会假装已经创建可联动的 Figma 实例。`componentDefinitions` 保存原始主组件，防止实际页面 DOM 覆盖破坏历史子节点引用。
- Lucide 图标与路径通过 SVG 转原生矢量；文字均为 TextNode；场景图为图片填充。没有将整页设计光栅化。
- 屋顶参数纠正为手动 0.8 秒、设备定位 0.5 秒、重置 0.55 秒。

## 原型边界

`prototype-links.json` 用真实源节点 ID 连接导航、查询、详情、回放与后台路径。50 号跨页退出确认原稿仅包含前往总览；需要生产交互记录继续原目标。28 自动连接、49 自动完成、43 登录错误、46 时间校验错误、52 查询/恢复失败为条件状态，其说明保留，未在普通标题上伪造点击。真实 3D、数据接口与连续回放动画由 UE 项目执行。

`verification.json` 是离线转换器/完整性核验，不是 Figma 真实导入证明。真实结果以导入插件下载的 acceptance JSON 和 Figma 视觉检查为准。图像 affine 裁剪按原矩阵保留，需检查实际渲染是否与源稿一致；字体替代也会在报告中明确列出。

## 官方接口依据

- [Plugin manifest](https://developers.figma.com/docs/plugins/manifest/)
- [Plugin API](https://developers.figma.com/docs/plugins/api/figma/)
- [官方 Plugin typings](https://github.com/figma/plugin-typings/blob/master/plugin-api.d.ts)
- [Prototype reactions](https://developers.figma.com/docs/plugins/api/Reaction/)

插件 `networkAccess.allowedDomains` 为 `["none"]`，不上传源文件或素材。`payload.json`、`ui.html` 为可重复生成的离线包。
