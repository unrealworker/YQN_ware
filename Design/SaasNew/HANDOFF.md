# SaasNew 设计维护交接

后续主设计源：[Figma · SaasNew](https://www.figma.com/design/AvRtQ9Hcbr1ttTF5dQx9Z1/SaasNew)。

最新增量更新（2026-10-29）：导航动效与像素流预览已直接写入现有 Figma 并回读验证，见 [本次规则](updates/2026-10-28-navigation-motion.md)。54 张画板旁说明、154 条普通导航连接及12处预览填充已更新；保留36条追溯确认路径。下面的4d3a214e验收记录和本地.fig属于首次迁移快照，不能用于覆盖本次实时更新。本次 MCP 不支持命名版本 API，因此仅声明实时文件写入和回读成功，不声明新增命名版本。

状态：**已完成实际导入、54 页导出、视觉与主要原型路径验收，并保存 Figma 命名版本。** 当前实际验收版本 `4d3a214e…`，记录见 `acceptance/final/SaasNew-acceptance.json`：54 画板、47 历史主组件、11 当前组件、12,229 画板节点、4,065 文字节点、1,063 条实际原型连接，全部 checks 为 true，错误 0；667 个过期节点已隐藏且清除交互，未删除。5 种字体/字重回退涉及 413 次使用，已在实际 01–30 页视觉复验中检查，没有造成可见缺字或溢出。最终结论见 acceptance/FINAL_ACCEPTANCE.md、实际验收 JSON 与视觉 QA 记录。

原 `Design/GHS_Twin_SaaS_Concept/Saas.pen` 作为历史来源保留；未来设计修改以 Figma 为主，不再默认回写旧 `.pen`。本目录保存本次迁移的来源、转换逻辑、交互说明与验收证据；UE 生产实现仍需独立开发与验证。

本地迁移插件用于本次受控迁移及修订，不是日常双向同步工具。后续直接维护 Figma 中的主设计；若再次使用插件，必须重新核对当前 Figma 编辑与旧迁移源，避免覆盖后续人工设计。

## 本次范围

- 全部 54 画板，含七个业务入口、详细状态、追溯、启动连接、管理后台与设计规范。
- 47 个历史主组件＋11 个最新 UE 页面组件，分开保留。引用展开为可编辑原生节点，避免文字与布局覆盖丢失。
- 最新 UE 页面几何、当前场景、回放轨迹、设备近景覆盖到对应画板；后台未接入页面明确标注设计阶段。
- 交互说明包含导航、面板、数据图表、屋顶、回放与退出确认；Figma 静态原型不能替代 UE 的真实 3D/数据接口。

## 验收顺序

1. 完成 Figma 原生节点导入，下载 `SaasNew-acceptance.json`，核对画板 54、历史组件 47、最新组件 11、文字/图片/连线检查及错误列表。
2. 点击插件“导出视觉核验包”，再手动点击“下载视觉核验 ZIP”。ZIP 中应有 54 张 Figma 实际 50% PNG、验收 JSON、导出清单。
3. 全量浏览渲染图；重点检查中文换行/粗细、最新场景底图、图表原生文字、回放时间轴、透明层、缩略图和滚动区域。
4. 在 Figma Present 中检查总览→库存/订单/设备/告警/追溯/场景、查询→订单→回放→结束、启动连接与后台设计路径。
5. 将实际验收结论、文件 URL、日期与剩余限制写回本目录；通过后才将状态改为“完成”。

## 本地开发插件注意事项

本地 manifest 已能在没有插件 ID 的情况下导入。私有 `setPluginData` 不适用于无 ID 插件，现已改为 `setSharedPluginData('saasnew', key, value)`；元数据不含凭据。

插件默认只接受新空白 `SaasNew` 文件，并支持本次已知导入的续传：首先核对源 SHA-256、三个固定页面及 shared pluginData，再按父节点内源 ID 逐层复用。尚未写入 owner 标记的第二次失败，使用 `resume-allowlist.json` 中实际错误报告的 47 主组件、11 当前组件和 40 画板 Figma ID 校验；任何未知分区、未知子节点或类型不符都会拒绝续传。完成及再运行会复用既有节点，不增加副本、不删除节点。

首次无 ID 私有数据失败留下的精确空骨架兼容保留。对象形式的边框宽度（如 `{top:1}`）已映射为四边 `strokeTopWeight` / `strokeRightWeight` / `strokeBottomWeight` / `strokeLeftWeight`，不再传入只接受数字的 `strokeWeight`。

2026-10-28 的视觉修订以 `acceptance/figma-render/SaasNew-acceptance.json` 中已完成的 `339ca017…` 为唯一跨哈希基线，`revision-allowlist.json` 固化其实际节点 ID 和原始节点归属树。新增源版本更新同源节点；源中不再使用的本次节点隐藏并清除交互，不移除，验收报告列出 `hiddenObsoleteNodes`。仍使用的节点会重置可见性；恢复旧源节点时可重新显示。全部原型连线设置后回读 Figma 的实际 reactions 验证，避免旧热点残留。

首次视觉修订 `eb0a9a8d…` 在原型连线阶段发现 4 条同画板导航，Figma 要求导航到不同的顶层画板。最新版本已在源数据去掉这 4 条连接，插件与 mock 均加入自导航预检。该次半完成版本单独列入 `allowedRevisionHashes`，仅当文档仍含原验收节点 ID 且 `revisionBaseHash` 为原 `339ca017…` 时允许续传。错误上报统一包装外部异常，保留具体 message、原 stack、阶段、当前源节点与可下载 JSON，避免只显示 catch 行。

执行插件时不要重建或覆盖正在加载的 `code.js` / `ui.html`。修复后关闭插件、构建验证、再运行。

提交与复现建议见 [DEPENDENCIES.md](DEPENDENCIES.md)。
