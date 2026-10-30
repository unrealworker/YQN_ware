# UE 5.8.4 升级执行记录

- 基线：`2bc8d04`，原项目 D:/UEPro/Test；新工作树 C:/Users/28109/.codex/worktrees/ue58-upgrade/Test，分支 codex/ue58-upgrade。
- 2026-10-30：确认引擎 5.4.4 CL35576357、5.8.4 CL58902052。新副本 Content 是真实 LFS 内容，没有指向原项目的链接。
- 原项目 NullRHI GHS 自动化：137 成功、0 警告、0 失败、0 未执行。该运行不包含 NonNullRHI 库容和实际视口 MapDrag，不视作完整功能验收。
- 首次受限运行在 Zen 子进程创建处被沙箱拒绝；使用正常本机权限重跑成功。不是项目基线缺陷。
- Ruling：保留 Legacy PixelStreaming，使用 5.8 原版作为插件底稿移植所有 GHS 补丁。理由：新版本仍提供该插件，现有输入和信令协议可保留；若接口判断有误，由原生测试和浏览器实连阻断交付。
- Ruling：独立副本关闭 StartupActions 自动 StarterContent 重导入，原 Content 已包含完整素材；避免新引擎首次启动覆盖手调资源。
- Ruling：打包脚本默认按 .uproject 的 EngineAssociation 定位已安装引擎；工具链由 TargetRules 决定，也可用显式参数覆盖。消除旧脚本强制 14.38 的冲突。
- Ruling：不复制旧 Saved/Intermediate/交付包到升级工作树；仅保留一个当前构建和小体积回归记录。
- 升级期间的自定义插件、输入 API、验证脚本可移植性分工并行实施，完整 UE 构建由主代理统一顺序运行。

## 当前状态

- 首次 5.8 Editor 编译准确失败于共享构建规则：V5 的警告/inline 设置与已安装引擎不一致，Unreal5_4 include order 明确标记 unsupported。改用 V7 / Unreal5_8，而不是强行覆盖共享引擎构建环境。
- GPU 诊断迁移到两版本均提供的 RHIGetGPUFrameCycles，保留无 RHI 时空采样语义，添加显式 RHI 模块依赖。
- Web UI 原有 141 项测试通过。像素流服务首轮 101 通过、1 个 SDP 文件加载失败，后经标准 vendor 准备后 109 项全通过；首轮失败记录保留。

## 已完成验证与运行差异

- 5.8 Editor 完整编译成功，包括 Legacy PixelStreaming 和 UE-MCP。使用 V7 / Unreal5_8，工具链默认值允许显式覆盖。
- 新版 JSON 使用共享字符串键，预算字段白名单显式构造等长 FString，保持原拒绝规则。
- 屋顶时钟在除法前饱和超大有限步长；原极值测试保留并通过，避免新编译器常量溢出报错。
- 自动化标志改为强枚举兼容写法，保留原 Editor/Client/Server/Commandlet 四上下文（不扩大到新 ProgramContext），原 137 个注册和断言不变。
- 原生真实 D3D12：138 项成功，0 失败、0 未执行。其中场景缓存测试记录一次 reserved resource virtual size 258GB / 256GB 告警；单独复跑该测试成功、0 警告。它不是物理显存占用数值。
- 编译警告揭示中文输入法实际回退：5.8 旧 EditableTextLayout 永远为空且 Shipping 不提供。改读真实 SlateEditableTextLayout，并新增真实 Slate composition Begin/Update/End 回归，实跑成功。
- Web UI 141、服务/播放器 109、启动器 54 项全部通过。服务首次失败是未准备 vendor 解压依赖，运行标准 build.js 后全通过。
- 真实 CEF 七页动效、图表、导航和窄屏检查通过；业务脚本按现行 UI 信息提示与数字到达目标等待修复，全部确认数值与示例标记断言通过。
- MapDrag 已兼容主场景 TwinHUD 与旧 TruckHUD 两入口；保留 20 个拖拽组合，真实主场景独立运行通过。
- GPU CSV 已适配 5.8 的 GPUTime 与实际 GPU pass 双重验证，屋顶和四态库容运行通过，没有把 Unaccounted 误作总 GPU 耗时。

## 收尾与用户接手

- Editor、Development Game、Shipping Cook/Stage/Archive 均成功。12 份真实场景脚本共 117 个检查项通过，证据和限制见 [验证记录](../../ue58-upgrade-validation-20261030.md)。
- Shipping 本地浏览器实际连接 1920×1080 H.264，验证全景、鼠标开顶、中文搜索与设备定位、追溯入口、刷新后同会话恢复。主场景资源哈希及 NonUFS 网页、数据、字体与源码一致。
- 用户最终明确“在本地验证……不用再往服务器上验证”，随后决定自行体验验收并要求今后使用 5.8 打开本项目。停止后续浏览器操作；两独立会话和完整浏览器追溯流程未完成，不记为已通过。
- 本轮不修改服务器。临时本地服务通过自身控制接口停止，测试浏览器 TaskSpace 关闭。
- 在确认原项目工作区干净后，将升级提交快进到 `D:/UEPro/Test` 的 `master`；`Test.uproject` 使用 `5.8`。原始源码回退点保留为 `2bc8d04`，UE 5.4 引擎仍保留；内容资产 1,075 个文件全部未改。
