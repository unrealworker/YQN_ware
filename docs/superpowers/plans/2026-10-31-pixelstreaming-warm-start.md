# 像素流预热与首帧优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 保留一个全新预热独立实例，并以预热命中时 5–10 秒实际显示首帧为验证目标。

**Architecture:** 服务端统一调度按需实例和一个备用实例。备用实例完成身份校验、PSO 预缓存和稳定运行后低负载待命，首次分配后永久转为用户实例，退出后销毁。客户端记录真实首帧及协商阶段，按实测定位等待。

**Tech Stack:** UE 5.8 PixelStreaming2、C++ 本地预算桥、Node.js 信令调度、WinForms 启动器、Epic WebRTC 前端。

**Spec:** 用户本轮已确认先实施预热实例与首帧阶段优化；本计划记录该已批准范围。

## Global Constraints

- 独立视角与控制；最多 5 个用户，备用计入实例上限，需求启动优先。用户本轮追加指令将原 10 人上限改为 5 人。
- 保留服务器现有 1920×1080、30 FPS、编码及 EIP/UDP 配置；不修改场景外观。
- 旧配置未含 warmStandbyEnabled 时保持关闭；本次部署显式打开。
- 不复用其他用户用过的场景状态，不修改原 8 秒断线宽限。
- 首帧以浏览器真实 video frame callback 验证，HTTP/信令成功不能代替出图。

## Review Focus

- 并发到达不得重复分配同一备用或突破 5 实例。
- 停止服务、故障和资源不足时不得出现预热重启风暴。
- 固定帧率只能对许可的未租用备用暂降至 5 FPS，租用必须恢复确认。
- 老配置、共享模式、重连、管理员踢出及 EIP 映射保持兼容。
- 前后台切换、重试及自动播放受阻不能伪报首帧或沿用上一轮计时。

### Task 1: 备用调度和预算协议

**Files:** server/service.js、server/resource-budget.js、Source/Test/GHSStreamingRuntime.{h,cpp}、对应 Node 与 UE 测试。

**Interfaces:** warmStandbyEnabled；启动许可 -GHSStandbyCapable；budget.mode 为 warming/standby/active；metrics.standbyMode；status.warmReadyCount/warmStartingCount/warmBlockedReason。

- [x] 写并运行并发租用、销毁补充、资源门限、故障退避和预算权限红测试。
- [x] 实现最多一个全新备用；身份/PSO/稳定指标达标后 5 FPS 待命，租用后恢复目标 FPS 并等待确认。
- [x] Node 测试与 UE Automation 通过，真实 Shipping 进程验证低负载及恢复。

### Task 2: 首帧计时与等待优化

**Files:** player/app.js、player 相关测试；必要的协商兼容代码。

**Interfaces:** ghsAdmission.warmHit/instanceId/timings；window.ghsStreamingStats 分阶段毫秒值。

- [x] 先测试真实显示首帧、重试重置、事件顺序及无首帧情况。
- [x] 检查 SDK 协商和订阅等待，仅修复有证据的延迟来源。
- [x] 本机真实预热首帧 1.938 秒、1920×1080、约 30 FPS、零丢包；服务器结果另行记录。

### Task 3: 启动器与交付

**Files:** launcher/Core.cs、MainForm.cs、SelfTests.cs 等；部署说明。

- [x] 加预热开关与就绪/准备中状态，验证配置兼容及布局。
- [ ] 完整测试、审查、中文 Git 提交，生成带清单和哈希的交付包。
- [ ] 在服务器零在线时更新，备份并仅对现有配置增加预热开关。
- [ ] 本机打开固定域名，测至少三个预热命中样本与一次冷启动，记录每阶段、真实首帧和稳定画面。
- [ ] 关闭自己的测试连接，验证其进程销毁且备用恢复一个；服务保持运行。
