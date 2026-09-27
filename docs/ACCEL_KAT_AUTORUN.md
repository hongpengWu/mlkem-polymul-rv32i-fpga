# KAT 无人值守续跑

更新时间：2026-09-27。当前方向是 **K=4 / ML-KEM-1024 主线，K=2 冻结历史对照，
K=3 后置扩展**；实板最后进行。旧“K3/K4 BaseMul 移植后返回 K2 优化”队列已撤销。
自动续跑 ID：`pqc-kat`，状态 **PAUSED**，间隔 **60 分钟**；本文件更新不恢复调度。
用户已授权本轮 HLS 建模、优化及审查后提交推送 `24-2hp`；原始分支和冻结基线不改。

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
2. [x] 更新性能表、覆盖矩阵、路线图。K3/K4 的128/32 KiB与512的64/16 KiB已分开列明。
   768 run_snapshot是事后归档：原run_inputs哈希仿真前捕获，额外源码只属事后快照。
   不改写历史哈希或伪称构建前证据。1024已补齐命令、源码、工具链和链接脚本哈希。
3. [x] 完成首轮 K=4 Keccak/FIPS 202 HLS 精确建模、访存优化和独立 IP OOC 实现。
   主加速器不受旧 BaseMul 范围限制；K=2 的 Keccak 71%–81% 占比只属于 K=2，K=4 尚未测量。
4. [ ] 补测 K=4 调用分布，再建立打包/批量接口、上下文协议与 CPU 集成，先代表性
   用例后完整官方 RTL KAT 145/145。
   主机、纯 CPU、局部 `hashlib` 差分或软件回退均不能替代对应加速系统的官方验证。
5. [ ] 完成同 RV32IM-fast、128 KiB RAM / 32 KiB 栈的未插桩端到端对照，计入搬运、
   启动、等待和读回，再完成同约束系统资源/时序及匹配产物。HLS 估算不能替代系统实现。
6. [ ] K=4 主线完成后再验证 K=3 扩展和其他 CPU 消融；K=2 历史对照继续冻结。
7. [ ] 完成适用异常/故障检查、系统回归和上板前验收，最后进行 PYNQ-Z2 实板和演示。

## 当前 K=4 HLS 进展及证据边界

- 目录 `hls/mlkem1024_keccak/` 支持 SHAKE128/256、SHA3-256/512；32-bit BRAM 输入/输出
  为 2048/4096 B，26 个 `uint64` 上下文，命令为 HASH/SQUEEZE/CLEAR。
- io0、io1 均已完成 C 仿真与 Verilog COSIM 的 109 笔本地 `hashlib` 差分事务，
  这不是 ML-KEM-1024 官方 KAT，也未证明 CPU 接入完成。
- 所选 `opt02` 优化版全 TB 实测 75,280 cycles，对照基线 1,314,553 cycles。HLS 优化版估算
  LUT/FF/BRAM18K/DSP = 15,244/15,385/2/0、时钟 8.895 ns；基线为
  14,612/17,008/2/0、8.622 ns。全 TB 周期不能直接当作完整 ML-KEM 加速比。
- 独立 IP `opt01` OOC 布局布线已通过当前10 ns时钟约束：WNS/WHS +0.279/+0.098 ns，
  LUT/FF=16,885/15,320，外部存储与CPU未计入；系统实现待测。`opt02` 只修正 LOOP_TRIPCOUNT
  上界且周期/资源相同，RTL 对比随报告归档。细节见 [HLS 说明](../hls/mlkem1024_keccak/README.md)
  和 [结果汇总](../results/hls/mlkem1024_keccak/summary.md)。

## 检查规则

暂停期间不自动启动新任务，也不因本文件更新恢复 heartbeat。下列检查规则只用于已在运行的
任务或以后明确恢复的调度：先读本文件，再查 vivado/xsim/xsimk/xelab/xvlog 和日志；
正常推进时静默结束，避免重复分析。
Read-Host、外层PowerShell存在、RUN_FINISHED不是成功判据。仅阶段完成、失败或需用户操作时通知。
可修复问题自主处理。历史可见控制台曾因文本选择暂停，Escape后恢复；当前stdout写日志。
CPU时间增长和有效ROW是进度证据，最终成功仍须PASS。
