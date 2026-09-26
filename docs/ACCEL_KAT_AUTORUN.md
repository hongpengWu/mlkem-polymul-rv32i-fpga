# KAT 无人值守续跑

更新时间：2026-09-26。用户已授权校验、汇总、扩展验证、清理并提交推送到 `24-2hp`；
原始分支和 ML-KEM-512 CPU-only 基线不改，实板最后进行。
自动续跑 ID：`pqc-kat`，按当前 automation 设置定期检查；电脑需保持开机、不休眠、Codex 运行。

## 已完成

- [x] 512 CPU+PQC：19 批、145/145 唯一覆盖，各批最终 PASS、实际 MMIO 指标和官方输出通过。
  缺失 0–37 已补齐，142–144 已按实际 3 条修复，不要重跑旧 14 批入口。
- [x] 独立证据位于 `results/accelerator_cpu/kat/`，默认 collector 通过；已提交推送 `0b16e76`。
  CPU-only / CPU+PQC 为 692,273,249 / 697,154,629 cycles，端到端 0.992998×。
  核心 46,240、搬入 14,404,780、读回 1,986,620、其余 API/驱动 680,716,989 cycles；后者不能全称轮询。
- [x] 768 RV32IM-fast CPU-only：2026-09-26 17:40 完成 145/145，collector 校验通过。
  算法周期 1,112,525,793，全程周期 1,147,835,590，最大观测栈 18,432 B。
  证据和表格在 `results/official_baseline/mlkem768/rv32im_fast/`。
- [x] K3/K4 参数化固件、fixture 和 TB 已建立，128 KiB RAM、32 KiB 栈。
  1024 RV32I/RV32IM 已编译；RV32IM-fast 官方 RTL 回归已 145/145 通过。

## 1024 RV32IM-fast CPU-only 已完成

- 已按 19 个顺序批次完成：0–7、8–15、…、136–143、144（最后 1 条）。
- 全量 collector 已通过：145/145 唯一覆盖，逐字节官方输出、返回值、M 指令、栈和输入哈希均通过。
- 汇总：算法 1,699,294,360 cycles，全程 1,747,426,461 cycles，最大观测栈 24,464 B；证据在 `results/official_baseline/mlkem1024/rv32im_fast/`。
- 每批证据：`results/official_baseline/mlkem1024/batches/rv32im_fast/batch_*/`。
  实时日志为 `console_<attempt>.txt`；`simulate.log` 可能缓冲至结束，不能因其为空误判停止。
- 构建目录：`build/mlkem_suite/1024/rv32im_fast/<batch>/<attempt>/`，重试使用新目录。
- 每批保存真实 case_count、original_indices、运行前输入哈希、最终 PASS 和 success.json；失败修复时保留旧 attempt。
  Windows 进程锁及活动 Vivado/XSim 检查防止重复调度。
- 新建 `build/mlkem_suite/STOP` 后，在当前批结束时停止启动下一批；恢复前移除标记。
  运行中禁止更改冻结脚本、TB、固件、manifest，禁止终止正常仿真或删除活动目录。

## 下一步顺序

1. [x] 1024 已执行 `python scripts/mlkem_suite/collect.py --parameter-set 1024 --write`。
   145 条唯一覆盖、每批最终 PASS、官方字节/返回值、M 指令、栈、周期和哈希全部通过。
2. [ ] 更新性能表、覆盖矩阵、路线图。K3/K4 的128/32 KiB与512的64/16 KiB分开列明。
   768 run_snapshot是事后归档：原run_inputs哈希仿真前捕获，额外源码只属事后快照。
   不改写历史哈希或伪称构建前证据。1024已补齐命令、源码、工具链和链接脚本哈希。
3. [ ] 完成K3/K4加速硬件移植和对应RTL官方回归。K=2专用核不能冒充支持K3/K4，
   主机、纯CPU或软件回退不能替代对应硬件验证。
4. [ ] 完成新系统所需Vivado实现，保留XPR、报告和烧录产物；只清理已停止的可再生缓存。
   审查差异后提交推送24-2hp，可阶段提交；未测项目保持待测，实板最后进行。
5. [ ] 全部授权步骤完成后删除heartbeat并简短总结。

## 检查规则

先读本文件，再查 vivado/xsim/xsimk/xelab/xvlog 和日志；正常推进时静默结束，避免重复分析。
Read-Host、外层PowerShell存在、RUN_FINISHED不是成功判据。仅阶段完成、失败或需用户操作时通知。
可修复问题自主处理。历史可见控制台曾因文本选择暂停，Escape后恢复；当前stdout写日志。
CPU时间增长和有效ROW是进度证据，最终成功仍须PASS。
