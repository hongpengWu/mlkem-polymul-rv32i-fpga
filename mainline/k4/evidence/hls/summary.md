# K4 Keccak HLS：功能与首轮优化

日期：2026-09-27。Vitis HLS / Vivado 2024.2，xc7z020clg400-1。
源码与入口：[专用目录](../../../hls/mlkem1024_keccak/README.md)。

## 同接口、同测试集对比

两配置 C 仿真、综合、Verilog COSIM 均通过。109 次事务包括 74 个 HASH 向量、
续取、交错上下文及无效调用。Python hashlib/OpenSSL 作为独立 oracle；这些是本地
FIPS 202 差分测试，不是官方 ML-KEM/ACVP 回归。

| 指标 | io0 基线 base02 | io1 优化 opt02 |
|---|---:|---:|
| COSIM 总周期（整个 TB） | 1,314,553 | 75,280 |
| 按相同 10 ns 换算 | 13.14553 ms | 0.75280 ms |
| COSIM 单事务 min / avg / max | 30 / 12,066 / 89,306 | 30 / 696 / 7,462 |
| HLS LUT 估算 | 14,612 | 15,244 |
| HLS FF 估算 | 17,008 | 15,385 |
| HLS BRAM18K / DSP 估算 | 2 / 0 | 2 / 0 |
| HLS 时钟估算 | 8.622 ns | 8.895 ns |
| HLS 最大延迟估算 | 247,935 cycles | 36,247 cycles |

同一 COSIM 工作负载周期比 **17.462×**（周期减少94.27%），LUT估算增加4.33%，
FF估算减少9.54%。主策略是分块打包访存及消除变量取模；两版均复用单轮Keccak数据通路。
HLS 时钟估计略变慢，实际运行目标均为100MHz，不按估算Fmax虚构系统频率。

COSIM 周期包含生成驱动的 AXI-Lite 参数设置、状态轮询和返回寄存器读取；
不是裸 Keccak-f 周期，也不是 PicoRV32/完整 KEM 周期。驱动跳过未变的参数写入，
同长度调用可能因前一事务的参数不同而出现17周期差异；不据此声称数据相关执行或恒定时间。
这些测试的负载权重也不是官方 K4 调用分布，因此 **17.462× 不能写成 K4 系统加速比**。
逐事务数据在 [transactions.json](transactions.json)。

| 代表性本地事务（输入→输出字节） | io0 COSIM latency | io1 COSIM latency |
|---|---:|---:|
| SHAKE128 34→504（矩阵 XOF 形状） | 3,421 | 831 |
| SHA3-256 1568→32（K4 H(ek) 形状） | 55,433 | 1,295 |
| SHAKE256 1600→32（K4 J(z\|c) 形状） | 56,553 | 1,316 |

## 独立 IP 布局布线

`opt01` 成功执行 `export_design -flow impl`，工具退出0；物理报告均已归档。

| 实现后指标 | 数值 |
|---|---:|
| Clock | 100 MHz / 10 ns |
| WNS / TNS | +0.279 ns / 0 ns |
| WHS / THS | +0.098 ns / 0 ns |
| Slice LUTs | 16,885 / 53,200（31.74%） |
| Slice Registers | 15,320 / 106,400（14.40%） |
| BRAM tile / DSP | 0 / 0 |

这是 **OOC 独立 IP**：输入/输出/context BRAM 是外部端口，未计入存储实体，也没有 CPU。
所以0个实现BRAM不代表完整系统无需BRAM；HLS内部ROM估算和Vivado最终映射也不同。
生成XDC仅定义10ns时钟，未定义外部I/O延迟；HD.CLK_SRC未指定，完整时钟树/偏斜待顶层集成。
DRC有独立Zynq IP缺少PS7的ZPS7-1警告。当前WNS只证明此OOC约束下内部路径满足要求，
不能代替CPU系统或板级时序。未产生新的完整系统bitstream；不发布默认活动率功耗为实测功耗。

[实现指标](physical_metrics.json)、[routed timing](opt01_impl/p/sol1/impl/verilog/report/mlkem1024_keccak_accel_timing_routed.rpt)、
[routed utilization](opt01_impl/p/sol1/impl/verilog/report/mlkem1024_keccak_accel_utilization_routed.rpt)。

## 来源、选择与恢复

- `base02`：冻结的同接口字节基线；`opt01`：打包IO及物理实现；`opt02`：最终所选源码。
- `opt02` 将长非对齐续取的 LOOP_TRIPCOUNT 最大值从1030更正为1055；这是综合估计注释，
  C/RTL重新通过109笔，实际COSIM周期和资源不变。15个综合文件逐一比较，仅顶层
  CORE_GENERATION_INFO 的延迟文字属性有差异，逻辑完全一致。比较哈希及唯一归一化规则
  见 [rtl_equivalence.json](rtl_equivalence.json)，据此保留opt01物理证据，无须再跑相同布局布线。
- 每份 `manifest.json` 保存运行前源码/TB/config哈希；`state.json` 保存阶段退出/报告哈希。
  `archive_manifest.json` 记录精选报告复制的来源和哈希，未改写历史清单。
- `snapshot/` 只保留核源和运行脚本；TB同当前仓库固定夹具，哈希可核对。
  原始外部运行在 `E:/hls/k4_io0/base02` 和 `E:/hls/k4_io1/opt01,opt02`。
- 更早的`base01`曾因HLS include参数引号失败，失败现场保留在E:/hls，不纳入成功统计。
- 最新collector增加CSIM完整109笔标记检查及COSIM统计口径说明；归档脚本也独立核查109笔。
  这些归档/校验脚本改动不修改已运行快照。HLS生成工程、RTL、IP、checkpoint和cache不推送。

可重新生成完整独立运行，方法见源码目录README。归档命令：

```powershell
python hls/mlkem1024_keccak/scripts/archive_results.py --baseline E:/hls/k4_io0/base02 --selected E:/hls/k4_io1/opt02 --implemented E:/hls/k4_io1/opt01 --destination results/hls/mlkem1024_keccak
```

归档目录已存在时拒绝覆盖；换新目录保存新实验。提交仅包括源码/TB/Tcl、必要证据和文档。

## 下一步

先量化K4实际调用次数、消息长度和CPU阶段占比，再设计批量缓冲和CPU接口。
接入后先跑代表性官方用例，再跑完整145条K4加速RTL回归；同RV32IM-fast、
128KiB RAM/32KiB栈测完整API及搬运、启动、等待、读回开销，再完成系统实现和实板。
K2的71%–81% Keccak占比不当作K4实测结论。
