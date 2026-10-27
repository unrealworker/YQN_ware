# 可复现依赖与 Git 提交建议

本轮只整理设计源、迁移工具与验收证据，不改 UE 生产代码/模型，不包括性能诊断。此清单不会执行暂存或提交。仓库忽略 `Design/*`，请使用 `COMMIT_FILES.txt` 的精确路径，避免对整个 `Design/` 或 `SaasNew/` 无差别强制加入。

## 精确清单

- `COMMIT_FILES.txt`：本轮新增文件的完整仓库相对路径，可供根代理逐项暂存。
- `COMMIT_MANIFEST.json`：每项的用途、体积、是否已受 Git 跟踪，以及应排除的生成物。
- `DEPENDENCY_ASSETS.json`：当前 28 个必需图片输入的尺寸、SHA-256 和路径，总计约 49.03 MiB。包含已跟踪的 9 张历史组件图片，不会再次复制。
- `asset-portability-audit.json`：54 画板、47 历史组件和当前组件的全部图片引用审计。

当前实际设计版本是 `4d3a214ec281ca37cf8f38247415b5072638b8090f7043f2bbb0fad21511b25d`，以 `acceptance/final/SaasNew-acceptance.json` 为实际导入验收。新增 QA 文档后重新运行审计脚本即可刷新精确清单；不要只编辑路径文本而遗漏依赖。

## 纳入范围

| 内容 | 纳入原因 |
| --- | --- |
| 根目录 `.cjs`、清单与交接文档 | 可重复的来源盘点、DOM/POI 转换、界面状态清理、资产审计 |
| `migration.pen.json`、`runtime-overrides.json`、迁移报告 | 可审查的最终原生节点输入与交互映射 |
| `figma-import/src/`、构建/核验脚本、manifest、原型连接 | 离线开发插件源码 |
| `figma-import/vendor/` | Lucide SVG 图标快照与许可证；本轮 69 个使用图标全部包含在 71 个图标快照内 |
| `resume-allowlist.json`、`revision-allowlist.json` | 本次安全续传的精确节点 ID 与旧源归属树 |
| `runtime/dom/`、`poi/`、`search/`、`context/` JSON | 实际 UE 页面、POI、搜索与相机状态输入 |
| `runtime/assets/` 及清单列出的场景/裁剪图 | DOM 原始图片和迁移实际图片；额外保留 `scene/racks-detail.png` 以保持准备脚本的条件分支一致 |
| `qa/` 中源检查脚本与文字核验报告 | 可重跑的布局核验 |
| `acceptance/final/` 的验收 JSON、visual manifest、QA 文档 | 实际 Figma 54 页导入/导出证据 |
| 早期验收 JSON 和已知失败报告 | 续传允许列表的来源证明；没有整包保存失败截图 |

## 排除范围

- `figma-import/payload.json`、`ui.html`、`code.js`：可由源码生成，前两者各约 71 MiB，重复包含图片 base64。
- 54 张实际 Figma PNG、导出 ZIP、联系表：留在本地交付目录，验收 manifest 保存导出信息。
- `runtime/screens/`、`runtime/sidebar/`、临时浏览器脚本、派生 HTML/PNG、缓存、备份、`node_modules/`。
- 无关 `WareProductData/`，以及用户手动场景改动。

## 上游与复现

已跟踪的上游输入保持原位：`Design/GHS_Twin_SaaS_Concept/Saas.pen`、`current-design.json`、`order-replay-navigation.json`、`Design/GHS_SaaS_Interactive_20261026/src/pages.json`，以及精确图片清单中的历史组件图。

```powershell
node Design/SaasNew/build-inventory.cjs
node Design/SaasNew/prepare-migration.cjs
node Design/SaasNew/figma-import/build.cjs
node Design/SaasNew/figma-import/verify.cjs
node Design/SaasNew/figma-import/verify-visual.cjs
node Design/SaasNew/audit-portable-assets.cjs
node Design/SaasNew/audit-commit-files.cjs
```

运行导入插件期间不得重新覆盖正在使用的 `code.js`、`ui.html`。当前素材和节点快照可离线构建，不要求安装 npm 依赖。只有新增快照外图标时才需要原型目录的 `npm ci`（锁定 Lucide 0.468.0），随后应保存新增图标路径。

迁移源含 19 个绝对图片引用。相同目录可以直接构建；更换盘符后先运行 `prepare-migration.cjs`，它通过 `__dirname` 重建路径。可选 `audit-portable-assets.cjs --stage` 会创建独立可搬移源副本和资产，不改当前源/导入包；该归档按需交付，不重复纳入本次 Git。

未来主设计源为 [Figma SaasNew](https://www.figma.com/design/AvRtQ9Hcbr1ttTF5dQx9Z1/SaasNew)。本地迁移包保存本轮来源和交付证据，不应在后续 Figma 人工编辑后直接重跑覆盖。
