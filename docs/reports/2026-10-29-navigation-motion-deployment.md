# 导航微交互、Figma与阿里云部署验收

## 已部署改动

源提交：`5cbf7b3` 优化导航高光即时响应与页面切换动效；`449b862` 更新像素流启动器与访问页园区预览图。分支 master。

导航接受点击后先更新前端选中状态，再通知UE。单一高光使用180ms translate3d平移，曲线cubic-bezier(.16,1,.3,1)，连续操作可改变目标。hover仅按钮背景100ms；按下图文70ms缩至0.96，松开140ms恢复。保留追溯退出确认及取消保护。

页面退出80ms、进入140ms，取消父子重复整页错峰；同页新增条目160ms、4px位移，逐项20ms、最多延后60ms。重复当前入口不重播，无变化的尺寸通知不重置高光。数字、图表及420ms侧栏规则不变。

源码定位到的旧问题包括250ms高光、120/200ms整页切换叠加300ms子组入场与最长210ms延后，以及无变化尺寸通知强制校准。最后一组内容名义稳定时间约630ms。这是代码层原因，不是网络往返时延实测值。

## Figma

[SaasNew](https://www.figma.com/design/AvRtQ9Hcbr1ttTF5dQx9Z1/SaasNew)已直接修改现有节点：

- 54张画板的通用旧动效说明均已覆盖；09动效规范及全局说明同步。
- 30组导航均保持单一高光；154条普通点击连接使用180ms Smart Animate，保留36条退出确认路径和所有原目标。无hover触发导航。
- 12处旧预览图替换为用户新图，使用FIT；实际3D底图和模型未替换。
- 同步启动器旧文案中3人替换连接、固定60FPS和旧码率与当前实现不一致之处：最多10人、满员拒绝新连接、无固定FPS上限、流畅档1/8/24Mbps。
- 回读：54/54说明更新，无说明溢出，无旧250ms导航文案；规范及预览截图已目视检查。

MCP实时写入和回读已成功；命名版本API不受支持，本轮不声称创建命名版本。保留历史Saas.pen、.fig及迁移验收快照，已更新本地HANDOFF说明避免旧源覆盖。

## 验证与部署

动效测试10/10、实际页面状态机140/140、播放器30/30、启动器52/52通过；构建、语法与diff检查通过。启动器18张GUI夹具图及嵌入PNG哈希核验完成；GUI夹具不代表真实服务器并发性能。

目标：阿里云Windows `10.100.185.161`，目录 `C:\YQN_WareHouse`。固定入口：[仓库像素流](https://warehouse-sim.iyunquna.com/)。

增量包：`Saved/UIMotionRefresh20261028/GHS-UI-Motion-449b862-Delta.zip`，7,555,327字节，SHA256 `efa802e4f0ba7a810842a57cdc6961c089042e26e12d401743d645a735025f23`。11个替换文件与manifest；200个管理文件应用前后逐一核验。

完整副本已执行预检、应用、全文件哈希检查、回滚预检及回滚恢复。更新器不写配置，fixture验证其字节和mtime不变。远端预检通过后实际应用成功，备份路径：`C:\YQN_WareHouse\_updates\Optimization-20261029-000905-d505d3c5`。更新脚本位于 `C:\YQN_UIMotion_20261028\MotionDelta`，可在停服后按Rollback-Optimization.ps1回退。

远端manifest源提交为449b86297487d9908136f3b728406e856c4f0adc；manifest SHA256 `1becdddbec3aead852dd86a1a77408fb1a9edaf03e61dc37b1333ea1e57a620c`。地图SHA256仍为 `1a28e3301d524bbb9aa0a32556e684d1468d4c7f095544e8a3430599e5a5aa01`。本机完整交付目录 `Package_PublicStreaming_Optimized_20261028` 同步为本版。

Windows自动扫描后新版启动器正常启动；可见新图。服务HTTP200，independent模式，上限10、访问保护关闭、FPS0，码率1/8/24Mbps保持。浏览器固定链接接入无需访问码，实际收到1920×1080播放视频。验证了hover保持总览选中、库存与设备入口可达、返回总览；快速切换逻辑另由单测验证，不将单张截图当作180ms逐帧流畅度证明。

通过固定域名下载的PNG SHA256与用户原图一致：`3f32e31d62dfb735d63e76d34523d8d7bf5cb59696b6bb0c55cdfbba8a5f8739`。

00:22:45北京时间最终检查：HTTP200、running、independent、viewerCount0、maxViewers10、accessRequiredfalse。测试连接已释放，服务保持运行。

## 限制

本轮没有更改网络或编码资源策略。00:17:59本机单次统计显示75.2fps、13.66Mbps、RTT13ms、缓冲12ms、解码0.43ms，但连接累计短暂停顿118次。该瞬时帧率和0%近期丢包不能证明整段无卡顿，更不能声明网络问题已解决。此次验收确认部署、访问、预览图和页面行为；不报告端到端输入延迟改善百分比或十人并发能力。

全部检查证据保存在 `Saved/UIMotionRefresh20261028/`，包含figma-result.json、delta-report.json、delta-verification.log、server-client-check.json、server-health-final.json及本机/远端截图。不包含访问码或控制令牌。
