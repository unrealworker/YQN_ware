# 192.168.150.14 像素流部署初步评估

调研日期：2026-10-23，Asia/Shanghai。目标项目：D:/UEPro/Test，UE 5.4.4，默认 GHS_CAD_NormalWarehouse_ZcoolSmartFactory。用户要求：每人独立操作、独立视角，分别评估 1920×1080 / 60 FPS 和 30 FPS。

本轮通过 SSH 只读检查服务器，并读取项目文件、已有测试记录与官方资料。没有安装组件、启动 UE 实例、修改服务器配置或进行压力测试。登录凭据不写入报告。用户本机的三人策略不作为服务器容量限制。

**结论：服务器具备承载该项目多实例像素流的硬件条件，值得部署验证；当前 Linux 环境和项目 Linux 产物尚未打通，人数只能作为条件估算，不能作为上线承诺。**

| 目标 | 保留现有高码率画质时，千兆出口的带宽预算 | 后续全机算力验证目标，非已证实容量 |
|---|---|---|
| 1080p / 60 FPS | 约 10–14 路；初步按 10 路做预算 | 先验证每卡 1 路、全机 10 路，再探索每卡 2 路、全机 20 路 |
| 1080p / 30 FPS | 约 14–20 路；初步按 15 路做预算 | 先验证每卡 2 路、全机 20 路，再探索每卡 3–4 路、全机 30–40 路 |

带宽预算不是 GPU 性能测试结果，也不是可交付并发。实际人数取 GPU 渲染、编码、CPU、内存、网络、应用调度所允许的最小值；任何一个条件不满足，实际人数都会下降。上表较高人数是用于设计压测梯度的假设，不是由 A40 实测推导的预测。

**服务器现场证据**

| 项目 | 本轮读取值 | 对部署的含义 |
|---|---|---|
| GPU | 10 × NVIDIA A40；各 46068 MiB 可见显存；300 W 功率上限 | 每卡独立分配 UE 进程；不能把十卡显存当成单一实例共享池 |
| GPU 占用 | 首末两次查询均为 GPU 0%、编码器 0%、显存 1 MiB，无运行 GPU 进程 | 仅表示调研时空闲，不代表 GPU 已长期预留给本项目 |
| NVIDIA 驱动 | 550.90.12；nvidia-smi 显示 CUDA 12.4 | 已有驱动；CUDA 版本展示不等于已验证 Vulkan 或 NVENC 实际会话 |
| CPU | 2 × Xeon Gold 6230R，26 核/52 线程每颗；合计 52 物理核、104 线程 | 全机 CPU 和单线程性能可能限制十卡扩展；超线程不能按物理核等价计算 |
| NUMA | 两个节点，GPU 0–4 位于节点 0，GPU 5–9 位于节点 1 | 实例的 CPU/内存应尽量绑定相邻节点 |
| 内存 | 471 GiB 总量、约 446 GiB available；无 swap | 相较低两位数实例，内存容量较充足，仍需测每实例峰值 |
| 当前负载 | load average 约 0.67 / 0.63 / 0.62；存在 Node、Java、MySQL 等其他服务 | 此服务器并非空白专用机器；需为原有业务保留资源 |
| 用户 cgroup | CPU quota = -1；内存 limit 为内核无限制哨兵值 | 没有观察到 user.slice 的额外 CPU/内存配额限制 |
| 网络 | em3 192.168.150.14/24：1000 Mb/s Full，默认出口；em4 为另一子网，也为千兆 | 两口未观察到绑定，不能直接按 2 Gb/s 计算；路径吞吐、公网带宽未知 |
| 网络瞬时观测 | em3 两秒观测约 TX 0.075 Mb/s、RX 0.172 Mb/s | 仅为当时背景流量，不是网络吞吐测试 |
| 系统 | CentOS Linux 7，kernel 3.10.0-1160.88.1.el7.x86_64，glibc 2.17 | 需要按 UE5.4 及实际依赖验证，不应套用 UE5.8 最低要求 |
| 系统图形库 | libnvidia-encode.so.1、libGLX_nvidia.so.0、libEGL.so.1 可加载；NVIDIA ICD 声明 Vulkan 1.3.277 | 驱动侧图形/编码库存在，但未创建渲染或编码会话 |
| Vulkan loader | ctypes.CDLL('libvulkan.so.1') 失败：No such file or directory；无 vulkaninfo | 当前系统环境未能加载 Vulkan loader；部署时必须提供可用 loader 并实际验证 |
| Node / Docker | Node 16.20.2；npm 8.19.4；Docker CLI 19.03.5；已有 NVIDIA Container Toolkit 1.16.1 | 运行环境较旧；本用户不在 docker 组，Docker daemon 查询被 socket 权限拒绝 |
| 磁盘 | 根目录 836 GiB，余 90 GiB；多个数据卷余约 195–959 GiB | 有部署空间，但应选合适数据卷；根分区已用 90% |
| 磁盘类型线索 | PERC H730P 逻辑盘报告 ROTA=1 | 不据此推断具体物理盘规格；冷启动、并发加载需另外测试 |
| 已用端口 | TCP 80 和 8888 已监听 | 部署选择空闲端口或接入现有反代，不覆盖已有服务 |

读取方法包含 lscpu、free、nvidia-smi、nvidia-smi topo、ethtool、ip route、df、lsblk、ldconfig、ctypes 动态库加载、cgroup 读取及 ss。ethtool 的只读唤醒配置项显示权限不足，但网口速率和双工状态成功返回。Docker 运行时/容器详情没有取得，不能视为已核实。

**编码与版本依据**

[NVIDIA 编解码矩阵](https://developer.nvidia.com/video-encode-decode-support-matrix) 和 [A40 资料表](https://images.nvidia.com/content/Solutions/data-center/a40/nvidia-a40-datasheet.pdf) 确认：A40 每卡一个第七代 NVENC，引擎支持 H.264，最大编码会话标注 Unrestricted，不支持 AV1 编码。Unrestricted 是没有该类会话数限制，绝不是吞吐无限。十张卡总计十个编码引擎，每个引擎可以承载多路。

[UE5.4 Pixel Streaming Reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-pixel-streaming-reference?application_version=5.4) 支持 Linux 与 NVENC，但列出的 Linux 测试系统为 Ubuntu 18.04/20.04。当前 [Linux Requirements 的版本历史](https://dev.epicgames.com/documentation/unreal-engine/linux-development-requirements-for-unreal-engine?lang=en-US) 把 UE5.3–5.4 对应到 Ubuntu22.04/CentOS7、v22 clang16 工具链，因此不能仅因 CentOS7 就断言 UE5.4 无法运行。

CentOS7 已于 2024-06-30 结束生命周期，见 [CentOS 官方说明](https://www.centos.org/centos-linux/)。为长期运行和现代依赖适配，建议规划受支持的 Linux 运行环境；当前机器还有其他服务，系统迁移属于另一个需要明确范围的工作。本轮没有执行升级。

项目 Windows 交付曾使用 Node24，不能直接把对应 Linux 官方二进制搬到 glibc2.17 上运行：[Node24 平台表](https://github.com/nodejs/node/blob/v24.x/BUILDING.md) 要求 Linux x64 glibc>=2.28、kernel>=4.18。服务器现有 Node16 是否能满足具体服务依赖没有运行验收。容器也共享宿主机内核，不能宣称换镜像就解决所有兼容问题。

**项目历史测量，仅用于认识负载，不作为服务器人数限制**

2026-10-21 的 [像素流验收记录](D:/UEPro/Test/Deployment/GHSPixelStreaming/验收记录.md:17) 来自 RTX5060 Laptop 8GB、UE5.4.4 Windows 包：

| 独立实例 | 浏览器实收 FPS | 其他证据 |
|---|---|---|
| 1 | 59–62 | 1080p；约 49–54 Mbps；恢复单实例后约 52–57 Mbps |
| 2 | 末段每路 32–33 | GPU 99%，显存约 6129 MiB；非零样本 29–33 FPS，码率 34.136–42.925 Mbps，均值 36.28 Mbps |
| 3 | 末段每路 21–22 | GPU 99%，显存约 7363/8151 MiB |

原始文件：[one-viewer.json](D:/UEPro/Test/Saved/PixelStreaming/Browser/20261021-quality/one-viewer.json)、[final-two-viewers.json](D:/UEPro/Test/Saved/PixelStreaming/Browser/20261021-quality/final-two-viewers.json)、[final-recovered-viewer.json](D:/UEPro/Test/Saved/PixelStreaming/Browser/20261021-quality/final-recovered-viewer.json)。接近 30 FPS 的码率是自适应降帧时的历史观测，不是本轮在 A40 上固定 30 FPS 的测试结果。

另有 [渲染性能报告](D:/UEPro/Test/docs/performance/2026-10-21-p0-p1.md:25)：1080p、100% 渲染比例、不限帧、每轮预热15秒后采样90秒、三轮。优化后 GPU 平均11.924ms，整帧 P99 17.336ms，GameThread 平均1.809ms/P99 3.347ms。第一轮最重总览 GPU 平均14.839ms/P99 20.497ms，见 [原始 summary](D:/UEPro/Test/Saved/PerformanceP0P1/Optimized01_20261021_031954/summary.json:794)。它没有证明严格稳定60FPS，也不包括像素流编码和远端网络。

这些测量与服务器的 GPU 架构、CPU、Linux/Vulkan 路径不同；不能用理论 FLOPS 比例换算并发，也不能把本机瓶颈照搬到服务器。项目包含仓库密集实例、透明/Decal效果、动态阴影和 CEF 页面，复杂视角与移动场景应纳入后续压力测试。

**网络预算的计算**

计算示例：网络路数 = floor(可分配出口 Mbps / (单路视频 Mbps × 1.15))。这里假设千兆路径实际可用，拿 700–800 Mbps 做规划，另给媒体协议、重传等取15%的示例系数。这不是已测得的可用带宽或固定协议开销。

- 60 FPS：历史约49–57 Mbps，对应约10–14路带宽预算。
- 接近30 FPS：历史约34–43 Mbps，对应约14–20路带宽预算。
- 若60 FPS编码目标调整为20–25 Mbps，20路约需460–575 Mbps（包含上述示例开销）。
- 若30 FPS编码目标调整为10–15 Mbps，40路约需460–690 Mbps。

降低码率保持1920×1080像素尺寸，但压缩画质可能变化，仓库货架细线、移动画面和HUD小字需目视验收。上述低码率是待验证目标，不是声称与现有50Mbps档画质完全相同。30 FPS也不能直接推定带宽或显存正好减半。

即使增加到万兆网络，也不会自动增加 GPU 渲染吞吐。内网跨交换机路径、公网出口、访问用户所在网络，以及可能使用的 TURN 中继都需单独验证；网卡协商1Gbps不证明端到端可持续达到1Gbps。[Epic Hosting Guide](https://dev.epicgames.com/documentation/en-us/unreal-engine/hosting-and-networking-guide-for-pixel-streaming-in-unreal-engine?application_version=5.4) 说明 TURN 需要承载实际媒体流量。

**部署适配项**

- 当前是 Win64 包和 Windows 启动器，需要 Linux x86_64 游戏包与服务管理入口。已经接入 Pixel Streaming，迁移重点是平台运行与多卡调度。
- [相机插件声明](D:/UEPro/Test/Plugins/UniversalCameraPlugin/UniversalCameraPlugin.uplugin:21) 只有 Win64/Android/LinuxArm64；[Test 模块](D:/UEPro/Test/Source/Test/Test.Build.cs:13) 直接依赖它。需验证并适配 Linux x86_64；有源码不等于已经兼容，缺白名单也不等于无法移植。
- CEF/HUD、中文字体、离屏渲染和浏览器输入需要在 Linux 实际验收。系统缺失 Vulkan loader 的检测也需在最终打包环境里解决。
- 部署时改用服务器会话策略，按 GPU 分配进程并与 NUMA 节点匹配。本机三人策略及按总人数分配FPS的旧规则可重新设置，不计入上述服务器容量。即使改掉人数常量，也仍须保证十卡实际得到合理分配。
- 固定帧率容量测试应避免自适应预算悄悄把60FPS降为30FPS后仍计入“60FPS并发”。30FPS测试同时限制UE渲染与WebRTC输出。

**建议下一阶段验证顺序，本轮未执行**

1. 先在一张 A40 上运行 Linux 包，实测1080p60和30各一路；验证Vulkan、NVENC、CEF、独立输入及最重视角。
2. 单卡逐步测试2、3、4个独立实例，记录GPU/编码器占用、显存、CPU/RAM、UE帧时间P95/P99、浏览器实际帧率、码率、丢帧及延迟。固定画质和帧率目标，不能以降帧成功代替容量成功。
3. 以单卡结果设置每卡配额，再扩大到十卡；全机测试必须覆盖52物理核、NUMA、网卡出口和原有服务的争用。
4. 使用独立物理客户端和实际访问链路，覆盖总览、货架近景、连续移动、HUD操作及多人同时进入；再做持续运行、断线回收与必要的TURN测试。

取得上述结果前，60FPS按10路、30FPS按15路做前期资源预算更稳妥；20路60FPS或30–40路30FPS应列为待验证扩展目标。实际稳定容量仍可能低于这些预算，尤其在复杂视角、网络瓶颈或平台差异出现时。
