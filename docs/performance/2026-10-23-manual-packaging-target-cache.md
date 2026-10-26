# Windows 手动打包的旧目标缓存修复

2026-10-23，编辑器执行 Windows Shipping 打包时传入 `-target=Test`，UAT 报 `Unable to find target 'Test'`。SDK 检查通过；报错发生于目标解析阶段，尚未开始项目编译或烘焙。

## 原因

- 当前真实目标为 `Source/TestGame.Target.cs` 和 `Source/TestEditor.Target.cs`；`Config/DefaultGame.ini` 已设置 `BuildTarget=TestGame`。
- 游戏目标曾因 `Test` 与 UE 构建配置同名而改为 `TestGame`，但 `Intermediate/TargetInfo.json` 和 `Intermediate/TargetInfo.Test.json` 仍保留 2026-10-15 的 `Test` / `Source/Test.Target.cs` 条目。
- 编辑器平台菜单通过 DesktopPlatform 的目标列表生成 `-target`。本机 UE 5.4.4 的 `IsPromotedBuild=1`；`DesktopPlatformBase.cpp` 的 `IsTargetInfoValid` 在该模式下直接接受缓存，未发现已更名的目标。
- `GetTargetsForProject` 还保留进程内缓存。更新磁盘文件后，需要保存当前工作并重新打开编辑器。

## 已执行修复

使用当前引擎的 UnrealBuildTool 重新查询实际目标，未手写目标条目：

```powershell
& 'D:\UE\UE_5.4\Engine\Binaries\ThirdParty\DotNet\6.0.302\windows\dotnet.exe' `
  'D:\UE\UE_5.4\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.dll' `
  -Mode=QueryTargets '-Project=D:\UEPro\Test\Test.uproject' `
  '-Output=D:\UEPro\Test\Intermediate\TargetInfo.json' -IncludeAllTargets
```

将同项目的 `TargetInfo.Test.json` 同步为生成结果。两个缓存现均只含 `TestEditor`（Editor）和 `TestGame`（Game）。原文件、原失败日志及本轮验证结果保存在 `Saved/PackagingTargetFix/20261023-manual-packaging/`。

## 验证边界

从新缓存取得 Game 目标并传给真实 UAT `BuildCookRun`，使用 Win64 / Shipping 参数，返回 `BUILD SUCCESSFUL`、`ExitCode=0`。完整日志确认 `ClientCookedTargets=TestGame`、`ClientConfigsToBuild=Shipping`，且 Build、Cook、Stage、Package、Archive、Deploy、Run 均为 False。

本轮验证了目标解析，未执行完整 Shipping 打包。当前编辑器未关闭，需要用户保存工作后重启一次，再通过原菜单打包。
