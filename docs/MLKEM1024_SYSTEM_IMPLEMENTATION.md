# K4 完整系统资源与时序对照

本轮直接综合、布局布线已通过官方KAT的完整系统RTL，保留RV32IM-fast、128 KiB程序RAM、
调试寄存器与总线；加速组还包含MMIO适配器、数据/上下文缓冲及Keccak核。
CPU-only源码和固件与原始官方基线哈希一致，加速组取自已通过的官方KAT冻结输入。
不修改两组RTL或固件，不重复功能回归。

两组条件相同：`xc7z020clg400-1`、10 ns时钟、0.1 ns不确定度、8线程；
`resetn`视为同步系统输入，输入/输出延迟预算均为min=0 ns、max=2 ns。
时钟入口假设`HD.CLK_SRC=BUFGCTRL_X0Y0`，不使用false path例外。

顶层拥有大量调试输出，当前按系统模块边界执行out-of-context（OOC）实现，
不将这些输出逐一绑定板上引脚。本结果覆盖CPU＋存储＋加速器内部资源和时序，
板级时钟/复位、外部接口、最终bitstream与实板验证仍须独立完成。
两组总线逻辑不同，因此资源差额表示整个集成系统的增量成本，不能全称为Keccak核成本。

入口：`python scripts/mlkem1024_keccak/implement_system.py`。
按加速组、CPU-only组依次执行综合→逻辑优化→布局→物理优化→布线。
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
主要失败路径是地址寄存器经MMIO offset/ready组合链到程序RAM地址。下一版优先将RAM写控制
从加速器ready反馈中解耦，验证组合等价性与RTL周期，再复验时序。
OOC resetn无HD.PARTPIN_LOCS导致边界hold不具备板级意义；已单独读取同一DCP的内部路径，
保留原始失败报告，不通过删除约束将其改写成PASS。
