# 前端 SDP 会话码率补丁

Epic UE 5.4 前端 `1.1.6` 的 `PeerConnectionController.mungeSDP()` 会在 H.264 SDP 中固定加入初始 `10000 kbps`、最高 `100000 kbps`。原方法同时用于浏览器 offer 和 answer，与本服务启动器设置不一致。

`build.js` 先校验 `dependency-pins.json` 内的归档 SHA512，再从归档提取原始依赖。`frontend-sdk-patch.js` 仅对生成的播放器 bundle 替换上述表达式，要求原 bundle 的 SHA256 和唯一表达式都匹配；SDK 升级会使构建失败，需重新审核补丁。`vendor/*.tgz` 和 `vendor/package` 原始源码均不修改。

播放器在创建 PixelStreaming 前把会话级 SDP 回调放入该会话 Config。它根据 `/api/session` 的最小、初始、最大码率生成视频 `x-google-*` 参数，统一从 Mbps 转为 kbps，移除旧值和重复值，保留编解码参数、RTX、ICE 和 SDK 原有音频处理。每个 Config 独立保存策略，重新协商时不累计参数。旧服务缺少初始字段时，兼容为限制在 min/max 范围内的 8 Mbps；新服务已显式返回该字段。

这些 SDP 参数是拥塞控制协商提示，不保证网络达到指定码率，也不是固定编码目标。服务端仍可根据网络/资源收紧预算。本补丁不改变 FPS、接收缓冲、候选地址、丢包处理或实际渲染负载，不能单独证明卡顿已解决。

复现构建与测试（项目根目录）：

```powershell
node Tools/PixelStreaming/build.js --output Saved/StreamingOptimization20261028/SdpNegotiationBuild
node --test Tools/PixelStreaming/tests/*.test.js
```

生成文件 `player/vendor/epic-sdp-patch.json` 记录原 bundle、结果 bundle、补丁脚本及码率策略文件 SHA256。生成的 vendor 目录不进 Git。测试加载实际 Epic UMD 与真实 Config/startSession/mungeSDP，并覆盖 offer/answer 发出的 SDP；仅替代浏览器媒体传输对象，不用伪造的协商实现。

部署时须同时更新服务的 session 字段、播放器 `app.js` / `stream-quality.js` 与生成的 SDK bundle。浏览器应建立新连接以完成新 SDP 协商。生产端是否采用新的 fmtp 值，仍需检查新连接 `getStats()` 的 codec `sdpFmtpLine` 并观察丢包、冻结、码率和帧率，不能只凭构建测试宣布网络改善。
