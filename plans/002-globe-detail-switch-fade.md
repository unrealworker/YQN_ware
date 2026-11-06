# 002 — 已选仓库之间切换详情时短淡换

- **Status**: DONE
- **Commit**: 18d64ee
- **Severity**: MEDIUM
- **Category**: Missed opportunities / Interruptibility / Accessibility
- **Estimated scope**: globe.js、必要 CSS、状态校验及浏览器测试。

## Problem

`D:/UEPro/Test/Content/GHSTwinUI/web/globe.js:87` 在已有详情中直接替换：

```js
$('name').textContent=w.name;$('city').textContent=w.city;$('address').textContent=w.address;$('thumbnail').src=w.thumbnail||'assets/warehouse-overview.png';
```

`panel()` 仅 inactive→active 时播放已有入场，GHS→MPR 的资料没有衔接。该操作暂按偶发使用，短淡换帮助确认目标变化。

## Target

- 只在已有有效选择 A→不同有效选择 B、详情持续展开、明确 pointer 来源时播放。
- 名称、导航面包屑、进入目标立即更新，不淡换旧身份、不延迟命令。
- 缩略图旧→新交叉淡换、城市/地址新内容 opacity 淡入，180ms，现有 `--ease-standard:cubic-bezier(.4,0,.2,1)`。
- 减少动效保留120ms纯透明度；keyboard 或 unknown 来源即时替换。
- 不动画面板尺寸/位置、指标数字、按钮位置；不重播初次详情展开或每次20Hz状态更新。
- 快速 A→B→A 从当前视觉态接续，异步图片加载晚到不能覆盖新目标；所有退场图片非交互且 aria-hidden，不制造重复 ID。
- 不增加等待图片或动效完成才能进入的门槛；图片失败有安全回退并清理旧层。

## Repo conventions to follow

- `D:/UEPro/Test/Content/GHSTwinUI/web/globe.css:1` 已有 standard 曲线。
- `globe.js` 使用原生 phase、ID 索引、WAAPI；既有 playMotion 在 reduced 模式直接跳过，新增功能应明确保留120ms透明度。
- 原生状态提供 `selectionInputSource`，CEF select/enter/back 命令传 `inputSource`。输入范围 pointer/keyboard/unknown；不读取旧焦点猜测来源。
- 当前 master 共享工作区，保留其他任务的改动。

## Steps

1. 在 `D:/UEPro/Test/Content/GHSTwinUI/web/globe.js` 追踪显式 pointer/keyboard 触发并传递到 select/enter/back；实现只对新选择ID触发、可中断的资料透明度过渡。
2. 必要时仅在 `D:/UEPro/Test/Content/GHSTwinUI/web/globe.css` 增加缩略图重叠层样式，复用现有 token。不改整体布局。
3. 在 `D:/UEPro/Test/Content/GHSTwinUI/web/globe-policy.js` 校验可选 `selectionInputSource` 枚举，保持旧宿主兼容。
4. 在 `D:/UEPro/Test/Tools/GlobeNavigation/tests/` 添加真实浏览器回归，验证及时身份/进入目标、180/120ms、键盘跳过、快速切换、晚到图片与清理。

## Boundaries

- 不重构其他动画、业务页面、国家标签、POI投影或地图。
- 不新增动效库、滚动计数、资料逐字显示、悬停效果。
- 与001原生输入来源接口协调，实施可并行，最终集成后验证。

## Verification

- Mechanical: `node --check Content/GHSTwinUI/web/globe.js`；`node --test Tools/GlobeNavigation/tests/policy.test.cjs`；在真实CEF执行新增浏览器测试并重跑既有POI测试。
- Feel check: 真实CEF按GHS→MPR→GHS切换，采样淡换早/中/结束帧；确认无白闪、旧图晚到、身份混淆、位置跳动；减少动效120ms，键盘无新动画。可在测试中将单次动画暂停到25/50/75%检查，不修改产品时长。
- Done when: 选择立即生效、资料在规定时长收束、图片层有界且清理、原生与CEF输入来源一致、进入返回正常。

## Result — 2026-11-06

- JavaScript 语法检查通过；策略测试 14 项通过。
- 真实 UE CEF 中既有 POI 测试 20 项、新增详情动效测试 18 项全部通过，覆盖快速反转、晚到图片、加载失败、场景清理与输入来源。
- 使用实际 GHS/MPR 图片检查 0/90/180ms 渲染帧：名称与进入目标即时更新，图片连续淡换，无白闪、布局跳动或残留层。
- 普通鼠标切换 180ms，减少动效 120ms，键盘与未知来源即时替换。
