# K4完整系统OOC实现对照

2026-09-27：两组完成综合和布局布线，资源均可容纳；**加速系统100 MHz内部setup未闭合**。
相同xc7z020clg400-1、RV32IM-fast、128 KiB RAM、10 ns时钟及0.1 ns不确定度。

| 系统 | Slice LUT | FF | BRAM36等效tile | DSP | 内部setup余量 | 内部hold余量 |
|---|---:|---:|---:|---:|---:|---:|
| CPU-only | 1,719 | 1,388 | 32 | 4 | +1.452 ns | +0.051 ns |
| CPU+Keccak | 19,084 | 16,970 | 34.5 | 4 | **−1.367 ns** | +0.050 ns |

加速组占器件LUT35.87%、FF15.95%、BRAM24.64%、DSP1.82%。增量包含接口与缓冲，
不全属于Keccak计算核。LUT使用report_utilization的packed数字，非原语简单计数。
两组所有可布线net均完成、无布线错误；check_timing无缺失约束，pulse width均+3.750 ns。
DRC无Error，仍有DSP流水建议及缺少PS7警告；板级集成另行处理。

加速组最差setup从local_awaddr_reg[22]到程序BRAM的ADDR[8]，经过adapter offset/ready
反馈与boot地址选择，10级逻辑，数据延迟10.663 ns，其中布线8.197 ns（76.9%）。
下一版优先将程序RAM写控制与加速器ready组合链解耦，随后简化对齐MMIO窗口译码。
本轮未改RTL/固件，原145/145及3.803×周期证据保持原版本，不宣称已在100 MHz实板实现该收益。

这是完整系统模块OOC，不是板级签核。resetn缺少HD.PARTPIN_LOCS，原始全路径hold为
CPU-only −1.190 ns、加速组−1.116 ns，均来自虚拟边界；上表另从同一routed.dcp查询
寄存器到寄存器路径，未用false path掩盖问题。原全路径指标和失败退出码保留，不改写成PASS。

冻结输入、综合/布线DCP保留在E:/hls/k4sys/20260927_194022/；Git仅收录脚本、约束、
原始报告及哈希。internal_audit/记录只读checkpoint复核，manifest明确为分析后归档。
