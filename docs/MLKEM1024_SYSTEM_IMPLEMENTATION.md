# K4 完整系统资源与时序对照

历史首轮直接综合、布局布线已通过官方KAT的完整系统RTL，保留RV32IM-fast、128 KiB程序RAM、
调试寄存器与总线；加速组还包含MMIO适配器、数据/上下文缓冲及Keccak核。
CPU-only源码和固件与原始官方基线哈希一致，加速组取自已通过的官方KAT冻结输入。
历史首轮未修改两组RTL或固件。2026-10-04开始对加速组RTL按关键路径优化，
CPU-only基线保持冻结；当前候选与历史全量验证范围分开记录。

两组条件相同：`xc7z020clg400-1`、10 ns时钟、0.1 ns不确定度、8线程；
`resetn`视为同步系统输入，输入/输出延迟预算均为min=0 ns、max=2 ns。
时钟入口假设`HD.CLK_SRC=BUFGCTRL_X0Y0`，不使用false path例外。

顶层拥有大量调试输出，当前按系统模块边界执行out-of-context（OOC）实现，
不将这些输出逐一绑定板上引脚。本结果覆盖CPU＋存储＋加速器内部资源和时序，
板级时钟/复位、外部接口、最终bitstream与实板验证仍须独立完成。
两组总线逻辑不同，因此资源差额表示整个集成系统的增量成本，不能全称为Keccak核成本。

统一入口为`scripts/mlkem1024_keccak/run_flow.tcl`顶部`IMPLEMENTATION`开关，
开发只实现当前加速组，不重复CPU-only；底层为`implement_system.py --keccak-source current --variants keccak`。
综合→逻辑优化→布局→物理优化→布线依次执行。
每轮使用新的短路径`E:/hls/k4sys/<时间>/`，其中保存冻结输入、完整控制台日志、
综合/布线DCP及约束。小型报告和SHA-256归档到`results/keccak_cpu/system_impl/`，
生成RTL和工程缓存不进入Git。当前断点记录在`build/keccak_cpu/implementation_progress.json`。

验收同时检查资源容量、setup/hold/pulse-width、未约束路径、DRC和布线完整性；
仅进程退出或`timing_met`字段不能替代全部检查。若未满足时序，保留失败报告，
先根据关键路径决定约束内的物理优化或RTL修改；改变计算/接口行为后再做对应功能回归。

## 2026-09-27首轮结果

两组均完成且资源可容纳；加速组内部setup −1.367 ns，CPU-only +1.452 ns；
内部hold分别+0.050/+0.051 ns。详见[完整系统实现报告](../results/keccak_cpu/system_impl/20260927_194022/summary.md)。

加速组LUT/FF/BRAM36等效/DSP为19,084/16,970/34.5/4；CPU-only为1,719/1,388/32/4。
主要失败路径是地址寄存器经MMIO offset/ready组合链到程序RAM地址；后续优化见下节。
OOC resetn无HD.PARTPIN_LOCS导致边界hold不具备板级意义；已单独读取同一DCP的内部路径，
保留原始失败报告，不通过删除约束将其改写成PASS。

## 2026-10-04 当前候选与迭代

- v1（`20261004_113341`）：RAM写控制与adapter ready解耦，高位译码；内部setup/hold
  −0.810/+0.050 ns，LUT19,024、FF17,000、BRAM34.5、DSP4。官方子集3/3的API周期与历史同例一致。
- v2（`20261004_120120`）：调整W通道接收后setup恶化为−1.059 ns，已回退该改动。
- 当前v3（`timing_decode_v3`）：保留v1，针对16 KiB对齐MMIO窗口用高位比较和低位截取替代宽减法；
  非对齐参数保留原范围/减法分支。组件10次调用/216字及译码等价检查通过；
  官方子集3/3（原索引0、1、115）通过，同例周期与历史完全一致，85次真实硬件调用匹配。
  [当前子集证据](../results/keccak_cpu/candidates/timing_decode_v3/kat/summary.md)。
  `20261004_121837`完成route_design后，在写入routed.dcp时异常退出（3221226356），
  未生成最终metrics；布局阶段WNS不作为最终结果。

失败日志保存在各自`results/keccak_cpu/system_impl/<批次>/`；DCP与冻结输入保留在短路径。
v1/v2全路径hold分别−1.280/−1.281 ns，OOC resetn边界问题继续单列保留。
恢复入口首次`20261004_124120`因过严的设计名称检查停止；修正为核对DCP元数据后，
`20261004_124354`从冻结综合DCP恢复，完成布线、报告及routed DCP保存。100 MHz内部
setup/hold为**+0.269/+0.029 ns**；LUT/FF/BRAM36等效/DSP为**19,003/17,005/34.5/4**。
全路径hold仍为−1.194 ns（resetn边界），故脚本按约定exit=1、`timing_met=false`，
同时`internal_timing_met=true`；不能将内部时序通过写成整体OOC或板级签核通过。
[恢复实现原始结果](../results/keccak_cpu/system_impl/20261004_124354/keccak/result.json)保存输入/报告/DCP哈希。
检查28,107/28,107可布线net全部完成、0布线错误；check_timing十二类检查均为0，
包括未约束内部端点；pulse-width最小裕量+3.750 ns、0失败。DRC仅7条警告
（DPOP-1×2、DPOP-2×4、ZPS7×1），没有错误。最差hold确认为resetn至cpu_state边界。
当前内部关键路径转为HLS FSM至state寄存器，9.606 ns中布线9.026 ns；
当前RTL/HLS哈希与smoke、官方子集、恢复实现输入一致。
开发只跑官方索引0、1、115及针对改动的检查，全部优化稳定后再执行145条最终验收；
历史145/145、3.803×不能替代当前候选的回归。
