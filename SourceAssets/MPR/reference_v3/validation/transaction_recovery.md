# 外景迭代的失败恢复

`mpr_reference_transaction.py` 不加载 Unreal，也不修改场景内存。导入器在首次写入任何输出包之前调用 `begin_transaction`，为本次计划写入的包、`.uexp/.ubulk/.uptnl`、当前 MPR 地图、所有权清单和 `Saved/MPR/reference_v3_build.json` 建立独立备份。每次都有唯一目录，保留的是本次运行之前的状态，不复用第一次导入的旧地图备份。

备份位于 `Saved/MPR/reference_transactions/<run-id>/`。`transaction.json` 记录原始 SHA-256、备份路径、计划输出和运行状态。失败处理调用 `record_failure`，记录每个计划文件失败后的实际 SHA-256，包括原来不存在而本次生成的文件。成功调用 `record_success`，成功事务不能通过失败恢复入口回滚。

导入器必须先写完最终失败报告，再调用 `record_failure`；记录失败哈希后不再改动报告或包。成功时也是先保存最终成功报告，再调用 `record_success`。这样恢复后会回到上一版成功报告，便于重新验收。

关闭所有 Unreal Editor 进程后运行：

```powershell
python Tools/MPRWarehouse/mpr_reference_transaction.py restore --transaction-dir "Saved/MPR/reference_transactions/<run-id>"
```

恢复会先检查全部备份是否完整、全部目标文件是否仍与失败记录一致。只要一个目标在失败后被编辑、删除或替换，就在修改任何目标前停止。运行中的 UE 或无法确认进程状态也会阻止恢复。

通过预检后，已有文件从本次备份逐文件原子替换；本次新增文件仅在内容哈希仍匹配失败记录时删除。未列入本次输出清单的文件完全保留，也不递归删除目录。恢复中断后，只有仍为“失败输出”或“已恢复原始内容”的文件才允许继续。

此工具处理捕获到的 Python 导入异常。若操作系统终止进程或机器断电，事务可能停留在 `prepared`；工具会拒绝把此时的未知文件状态自动认定为失败输出，需先人工审查，不能绕过哈希检查。

13 项隔离临时文件测试覆盖原文件和 sidecar 恢复、新输出删除、用户改动保留、UE 进程阻断、备份损坏、每次运行独立备份、恢复中断续作及路径范围。测试不会触碰实际 UE 包。
