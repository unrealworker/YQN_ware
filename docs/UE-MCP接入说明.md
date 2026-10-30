# UE-MCP 接入说明

本工程集成 [db-lyon/ue-mcp](https://github.com/db-lyon/ue-mcp) 的 `1.4.11` 源码桥接插件，目标为 Windows Unreal Engine 5.4.4。

## 工程内容

- `Plugins/UE_MCP_Bridge`：上游桥接插件源码及 MIT 许可证；编译输出不入库。
- `Test.uproject`：启用桥及必要依赖。
- `ue-mcp.yml`：工程共享配置，关闭反馈提交工具、需要 UE 5.5 的 StateTree 工具及仅支持 UE 5.8 的原生 Epic 工具。
- `ue-mcp.local.yml`：个人覆盖配置，已加入 Git 忽略。

本次使用 npm 发布包 `ue-mcp@1.4.11` 部署插件。安装器版本记录位于插件目录的 `.ue-mcp-install.json`。上游发布包有 UE 5.4 编译兼容缺口，本工程补充了头文件路径、GPU 回读同步、子系统快照遍历和资产差异 API 的兼容处理。升级或重新部署插件可能覆盖这些本地补丁，必须重新编译和验证后使用。

## 本机安装位置

- MCP 服务：`C:\Users\28109\.codex\mcp\ue-mcp\node_modules\ue-mcp`
- Codex 配置：`C:\Users\28109\.codex\config.toml` 中的 `[mcp_servers.ue-mcp]`
- 安装前配置备份：`C:\Users\28109\.codex\config.toml.before-ue-mcp-20261030.bak`
- 编辑器：`D:\UE\UE_5.4\Engine\Binaries\Win64\UnrealEditor.exe`

Codex 通过本机 Node.js 直接启动已安装的固定版本，参数为服务 `dist/index.js` 与本工程 `Test.uproject` 的绝对路径。新机器需自行安装服务并配置路径；用户目录配置和 npm 依赖不进入工程仓库。官方客户端配置参考：<https://learn.chatgpt.com/docs/extend/mcp?surface=cli>。

## 编译与连接

升级插件后，先保存工作并关闭编辑器，再编译：

```powershell
& 'D:\UE\UE_5.4\Engine\Build\BatchFiles\Build.bat' TestEditor Win64 Development '-Project=D:\UEPro\Test\Test.uproject' -WaitMutex -NoHotReloadFromIDE
```

本工程 `TestEditor.Target.cs` 已指定 MSVC `14.38.33130`。编译成功后打开 `Test.uproject`，等待地图加载完成。桥仅监听本机回环地址，实际端口见 `Saved/UE_MCP_Bridge/port.json`。

Codex 需要重新加载 MCP 配置才会展示新工具；若当前聊天未显示，可开启新聊天。默认使用 `micro` 工具集，通过 `tools` 网关发现和调用操作。只读连接检查：

```json
{"action":"call","category":"project","method":"get_status"}
{"action":"call","category":"level","method":"get_outliner","args":{"limit":5}}
```

必须同时验证 MCP 握手、`editorConnected: true` 和当前地图的 Actor 返回。仅安装完成、工具列表可见或 DLL 文件存在，均不足以证明编辑器已连接。排错参考：<https://ue-mcp.com/docs/troubleshooting/>。

自动反馈提交已禁用，验证连接无需创建、修改或保存任何场景资产。

## 本机验证记录（2026-10-30）

- UE 5.4.4 的 `TestEditor Win64 Development` 完整编译、链接通过。
- 使用独立无人值守编辑器及临时挂载资产，运行 `UE.MCP.PCG` 和 `UE.MCP.Diff.CheckpointAsset.MaterialGraphPropertiesAndThumbnails`，18 项全部通过（其中 15 项有测试临时资产相关警告，失败为 0）。
- 中文编辑器的资产属性标签测试使用当前引擎反射标签；PCG 测试在 UE 5.4 使用可用的三元运算检验动态引脚断线行为。
- 编译日志、自动化报告及连接验证 JSON 位于本机 `Saved/UeMcpSetup`，不提交到 Git。
- 上游在 UE 5.4 明确跳过 48 个 StateTree 方法，本工程不向客户端提供该分类。上游状态中的参数规格比对仍可能列出这些方法；这不表示桥接 DLL 未编译或通用连接失败。
- 以 Codex 配置的启动命令进行独立 MCP 客户端验证：初始化、工具发现、`project.get_status` 和 `level.get_outliner` 均通过；`editorConnected=true`、`pluginStale=false`，桥接地址为 `ws://127.0.0.1:62818`。
- 实际返回场景 `GHS_CAD_NormalWarehouse_ZcoolSmartFactory`、376 个 Actor，并读取其中 5 个；查询前后工程描述文件 SHA256 一致，场景资产无 Git 改动。此验证不等于所有上游功能均已逐项测试，也不证明当前 Codex 聊天已刷新原生工具列表。
