# SpongeBob UE 导入

- 原始文件：`D:\BlenderModel\spongebob-3d.blend`（未修改）。
- 角色集合：`3D | Character`；85 个网格/曲线部件合并为静态网格，保留 17 个材质槽。
- 程序化海绵斑点烘焙为 2048 × 2048 颜色贴图。
- 高度：180 cm，原点位于双脚底部中心；这是静态展示 Actor，不包含骨骼动画。
- 网格：`/Game/SpongeBob/Meshes/SM_SpongeBob`。
- 可复用 Actor 蓝图：`/Game/SpongeBob/Blueprints/BP_SpongeBob`。
- 默认关卡：`/Game/Maps/SpongeBobScene`，场景中的 Actor 名称为 `SpongeBob`。

## 编译

UE 5.4 使用本机已安装的 MSVC 14.38，避免自动选择较新的不兼容工具链：

```powershell
& 'D:\UE\UE_5.4\Engine\Build\BatchFiles\Build.bat' TestEditor Win64 Development '-Project=D:\UEPro\Test\Test.uproject' -WaitMutex -NoHotReloadFromIDE -CompilerVersion=14.38.33130
```

## 重新导入

先关闭此工程的 UE 编辑器，然后依次运行（会更新同名资源与展示关卡中的 SpongeBob）：

```powershell
& 'D:\WinAPP\Blender\blender.exe' --background --factory-startup --disable-autoexec 'D:\BlenderModel\spongebob-3d.blend' --python 'D:\UEPro\Test\Scripts\export_spongebob.py'
& 'D:\UE\UE_5.4\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' 'D:\UEPro\Test\Test.uproject' '-EnablePlugins=PythonScriptPlugin,EditorScriptingUtilities' -run=pythonscript '-script=D:\UEPro\Test\Scripts\import_spongebob.py' -unattended -nop4 -NullRHI
```

导入、C++ 编译与独立蓝图编译日志保存在工程 `Saved/Logs/SpongeBob_*.log`。

导入完成时有 2 条非致命的 MikkTSpace 切线/副法线警告。当前材质只使用颜色、粗糙度和金属度，没有法线贴图；以后增加法线贴图前，应检查并修复局部退化 UV。独立蓝图编译为 0 错误、0 警告。
