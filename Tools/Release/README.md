# Windows 版本与累计补丁

后续小修和兼容功能默认发布补丁，不再把整个 Windows 安装目录重新压缩分发。构建入口为本目录的 `release.py`，版本记录为 `releases.json`，安装入口为 `Apply-WarehousePatch.ps1`。所有发布操作在 `master` 执行。

补丁仍需建立在完整安装包上，不能独立运行。UE 的编译、Cook、补丁制作和最终分发是不同步骤：C++ 改动仍需编译，内容改动仍需 Cook；最终交付只包含相对固定基线变化的容器、程序或松散文件。

## 当前版本

| 版本 | 来源 | 用途 |
| --- | --- | --- |
| `1.0.0` | `287f6c3`，原 `GHS_GlobalWarehouse-Fixed` 全量包 | 当前部署版本，也是不可变补丁基线；包含首页/标签、屋顶溶解和 MPR 面板修复 |
| `1.0.1` | `c0dc238`，浅色地球改动 | 相对 `1.0.0` 的首个累计补丁；用户要求保留、稍后部署 |
| `1.1.0` | `6f301c2`，游戏内容来自 `5750de3` | 登录与双仓库选择、GHS 真实库位库存与取货回放。支持从 `1.0.0` 或 `1.0.1` 升级 |

`1.0.1` 的制作复用已经完成的浅色地球 Cook，不为建立版本管理再次全量编译。2026-11-17 已在原 `1.0.0` 的独立副本上完成补丁安装、实际 Shipping 像素流画面验证和回退；回退后全部 166 个基线文件 SHA256 一致。三个原生差分容器合计 258,937 字节，交付 ZIP 为 186,733 字节。安装器 15 项检查与基线保护 4 项测试通过。当前状态为 `verified`，尚未部署到原服务；证据路径与校验值记录在 `releases.json`。

## 版本号与状态

使用 `主版本.次版本.修订号`，例如 `1.0.2`，按顺序递增，已登记版本不得覆盖重用。

- **PATCH**：修复、配色、文案、配置等兼容调整，例如 `1.0.1 → 1.0.2`。
- **MINOR**：增加兼容功能，例如 `1.0.2 → 1.1.0`；仍可基于同一个兼容全量基线制作累计补丁。
- **MAJOR**：引擎升级、内容格式或运行兼容性变化，例如 `1.x → 2.0.0`；建立新的全量基线。

改变 UE 引擎构建、基础容器结构或脚本不支持的内容删除，需要重新评估基线。确需全量发布时说明具体原因，不能因补丁制作失败就自动退回全量打包。

`releases.json` 区分发布记录和实际部署：

| 状态/字段 | 含义 |
| --- | --- |
| `registered` | 已登记并校验完整基线，未表示进行了新的部署 |
| `built` | 补丁文件已生成、文件与 ZIP 校验通过，尚未代表运行画面通过 |
| `verified` | 在基线副本安装补丁后，已验证实际 Shipping 程序及相关功能，并记录验证材料 |
| `deployed` | 已在目标安装目录完成更新和运行确认 |
| `activeBaseline` | 后续补丁所依据的完整基线版本 |
| `deployedVersion` | 目标服务目前实际运行的版本；制作或验证候选补丁不改变此值 |

当前脚本自动追加 `registered`/`built` 记录。维护者应在完成相应验证或部署后补充状态和证据、更新 `deployedVersion`，再提交版本记录；不能仅凭构建成功标记 `verified` 或 `deployed`。安装器在目标目录写入 `warehouse-version.json`，但不会自动修改源码仓库中的版本记录或重启服务。

## 目录与保存规则

| 路径 | 内容 |
| --- | --- |
| `Deployment/Releases/1.0.0/package/` | 已有完整包的独立副本，不随线上安装目录更新 |
| `Deployment/Releases/1.0.0/Windows/` | 供 UE 补丁生成使用的原容器和原包中提取的 `AssetRegistry.bin` |
| `Deployment/Releases/1.0.0/baseline.json` | 原始文件大小、SHA256、引擎身份和源提交 |
| `Deployment/Patches/1.0.1/` | 补丁清单、安装器、安装说明及 `payload/` |
| `Deployment/Patches/YQN-Warehouse-1.0.0-to-1.0.1-Win64-Patch.zip` | 可交付补丁 ZIP |
| `Saved/PatchStaging/<版本>/` | UE 制作补丁的临时 stage，不直接整体归档分发 |
| `Saved/Packaging/Versioning/<版本>/` | 增量 Cook 与补丁制作日志 |

保留完整基线、已交付补丁及校验记录，直到正式淘汰该基线。不能用最新 Cook 的注册表覆盖旧版本注册表，也不能覆盖已登记的容器。版本脚本会校验基线身份、引擎版本、文件大小和 SHA256；版本或输出目录已存在时会停止，需要先检查原结果或失败日志。

## 登记已有完整包

以下命令以本机路径为例，在项目根目录的 PowerShell 中执行。UE 使用工作区外的日志和缓存；在 Codex 中执行 UE 相关步骤时，遵守项目 `AGENTS.md` 的命令级权限要求。

```powershell
$releasePython = 'C:\UE\UE_5.8\Engine\Binaries\ThirdParty\Python3\Win64\python.exe'
$releaseScript = 'C:\UEpro\warehouse\Tools\Release\release.py'

& $releasePython $releaseScript register-base `
  --version 1.0.0 `
  --package 'C:\UEpro\warehouse\Deployment\Windows\GHS_GlobalWarehouse-Fixed' `
  --source-commit 287f6c3 `
  --notes '当前运行的首页及屋顶修复版；从已有完整包建立补丁基线'
```

这是已有包的登记示例，`1.0.0` 已登记后不要重复运行。`register-base` 复制并核验已有完整包，提取该包自身的注册表，不重新编译或 Cook，也不修改原安装目录。`--source-commit` 仅记录构建来源，不会切换 Git 提交，必须填写与包实际一致的提交。

以后确需新完整基线时，说明不兼容原因，使用新版本执行 UE 的完整构建及 `-CreateReleaseVersion=<新版本>`，保留该次 Release 注册表、Cook 元数据和原始容器；验证后再用 `register-base` 登记实际完整包，并更新版本记录。旧 `1.0.0` 是从历史包迁移的基线，不能据此声称已拥有它当年的 `DevelopmentAssetRegistry.bin`。

## 制作补丁

正常后续版本只使用 `build-patch`，例如下一个修订版：

```powershell
& $releasePython $releaseScript build-patch `
  --version 1.0.2 `
  --base 1.0.0 `
  --notes '填写本次修复、影响范围和验证重点'
```

准备版本时核对源码与提交，避免把不相关的未提交工作混入发布。默认记录当前 `HEAD`；清单另外记录已有跟踪文件的工作区改动，不能用一个提交号掩盖实际构建差异。需要其他引擎安装路径时，把 `--engine '引擎目录'` 放在子命令之前；引擎构建必须与基线一致。

脚本分两步调用 UE：

1. `-build -cook -iterate` 增量编译并 Cook 登录入口、地球、GHS 和 MPR 四个关卡及其依赖。
2. `-skipbuild -skipcook -stage -pak -iostore -generatepatch -basedonreleaseversion=<基线>`：使用第一步产物制作原生 UE 补丁，单独筛选补丁容器和变更文件。

UE 不允许把 `-iterate` 与 `-basedonreleaseversion` 放在同一构建阶段，因此必须分开；不要重新合并参数。脚本不把整个 stage 执行 `-archive`，也不把基础引擎、CEF 或原始容器一起压入补丁。

首个 `1.0.1` 可按下面的迁移命令复用已验证的 LightGlobe Cook：

```powershell
& $releasePython $releaseScript build-patch `
  --version 1.0.1 `
  --base 1.0.0 `
  --source-commit c0dc238 `
  --reuse-cooked-from 'C:\UEpro\warehouse\Deployment\Windows\GHS_GlobalWarehouse-LightGlobe' `
  --notes '提亮地球海洋与背光区域，匹配浅蓝首页；待部署'
```

此迁移命令只适用于当前 staging 文件仍与指定完整包相符、且本机 Zen Cook 数据仍存在的情况。已登记 `1.0.1` 后不要重复运行；未来改动默认走正常增量流程，不复用失去来源对应关系的 Cook。

补丁大小由实际变化决定：

- **C++**：增量编译后交付变化的 EXE/DLL；不是只发材质容器。
- **材质、贴图、地图**：生成包含变化资源及必要依赖、着色器的原生补丁容器；不保证一个材质只产生一个资源文件。
- **NonUFS HTML、CSS、JS、JSON**：按哈希选择变化的松散文件，未变化的 UI 和 CEF 文件不重复交付。

工具支持项目当前的单组 `Test-Windows_0_P.pak/.utoc/.ucas` 补丁容器。UE 5.8 的全局脚本对象表变化时，生成器校验既有对象的标识、名字及引用关系。所有旧记录都保留且兼容时，补丁同时携带 `global.utoc` 和 `global.ucas`，安装器会备份两份基线文件以供回退。其他基础容器发生变化、全局表出现不兼容变动、拆分容器或删除基线松散文件时，需要重新评估基线。

## 验证、安装与回退

先在 **`1.0.0` 完整基线副本**上安装补丁并验证实际程序。原始 LightGlobe 全量包不是 `1.0.0`，不能把它作为 `1.0.1` 补丁的安装目标。检查默认首页、仓库标签、受影响功能，以及需要时的像素流启动。验证成功后记录证据，再安排正式更新。

正式更新前停止目标 UE 程序和对应像素流实例，并避免维护期间重新拉起旧程序。安装器会检查目标目录中的运行进程，**不会自动停止或重启服务**。把补丁 ZIP 解压到安装目录之外，然后先检查：

```powershell
$patchDirectory = 'C:\UEpro\warehouse\Deployment\Patches\1.0.1'
$installDirectory = 'C:\UEpro\warehouse\Deployment\Windows\GHS_GlobalWarehouse-Fixed'

& "$patchDirectory\Apply-WarehousePatch.ps1" `
  -PatchDirectory $patchDirectory `
  -InstallDirectory $installDirectory `
  -CheckOnly
```

`-CheckOnly` 核对版本、文件和进程状态，不写入安装文件。通过后去掉该参数安装：

```powershell
& "$patchDirectory\Apply-WarehousePatch.ps1" `
  -PatchDirectory $patchDirectory `
  -InstallDirectory $installDirectory
```

安装器检查补丁与基线文件的 SHA256，保存需要替换的原文件备份，并记录已安装版本。对于同一基线，补丁是 **累计** 的：`1.0.2` 已包含相对 `1.0.0` 的全部变化，可直接从 `1.0.0` 或该基线下较早补丁升级。安装器管理并替换上一组补丁，只保留一组当前累计容器；不要手工堆叠、改名或复制 `_P` 文件，也不要手动删除 `.warehouse-patch` 的备份和安装记录。

安装完成后启动程序或像素流服务，观看者重新进入页面；确认真实运行版本后再将发布记录改为 `deployed`。当前用户选择稍后部署 `1.0.1`，生成补丁不会自动替换正在运行的 `1.0.0`。

需要回退时，先停止目标程序，再执行：

```powershell
& "$patchDirectory\Apply-WarehousePatch.ps1" `
  -Rollback `
  -InstallDirectory $installDirectory
```

`-Rollback` 移除当前受管理补丁并恢复**最初完整基线 `1.0.0`**，不是回到前一个补丁版本。若安装复制过程中出错，脚本尝试恢复本次操作前的文件；如报告恢复不完整，保留事务目录并处理错误，不要继续启动程序。

## 本机 Cook 数据

当前 UE 使用 Zen Cook 存储。`Saved/Cooked/Windows` 中的 metadata 和 `ue.projectstore` 不是完整、可搬迁的 Cook 快照，不能仅复制该目录就假定其他机器可以 `-skipcook`。`ue.projectstore` 含本机认证信息，**绝不能提交或分发**。发行物只包含脚本筛选的补丁文件、清单和安装器；不要把整个 `Saved` 或 Zen 连接文件加入发行包。
