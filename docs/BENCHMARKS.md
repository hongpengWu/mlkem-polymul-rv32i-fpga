# 性能与资源数据台账

本文件集中记录可用于竞赛报告的实测数据。每组数据必须注明配置、计时边界和证据；未测项写“待测”，不得用理论估计或仿真数据代替实板结果。周期来自 RTL 仿真，资源与时序来自 Vivado 布线后报告。

竞赛目标、阶段门和创新路线见 [COMPETITION_ROADMAP.md](COMPETITION_ROADMAP.md)；本文件只登记已经测量或明确标记为待测的数据。

## 0. CPU 软件 baseline（本轮）

本轮首先解决 CPU 对照问题：三组使用同一份普通 C 软件 NTT/BaseMul/INTT 实现、同一组 8 个输入、同一独立直接卷积 oracle、同一 16 KiB CPU RAM 和同一 `-O3` 编译约束。PQC 硬件加速器没有接入这组测试。每个配置完成 8 个多项式、两次计时运行和 4096 个输出系数检查；输入生成、校验和输出串流均在计时区间外。完整协议见 [CPU_BENCHMARK_PROTOCOL.md](CPU_BENCHMARK_PROTOCOL.md)，原始日志和逐 case CSV 见 [CPU baseline results](../results/cpu_baseline/)。

| 配置 | CPU 参数 `MUL/FAST_MUL/DIV` | 固件 ISA | 未分段总周期（8 case 最小/平均/最大） | 分段总周期平均 | 计时空区间 | 每个算法窗口 M 指令 | 正确性 |
|---|---|---|---:|---:|---:|---:|---|
| RV32I | `0/0/0` | `rv32i/ilp32` | 2,604,377 / 2,838,815.9 / 2,896,797 | 2,838,818.9 | 4 | 0 | PASS |
| RV32IM 迭代 | `1/0/1` | `rv32im/ilp32` | 912,319 / 912,319 / 912,319 | 912,325 | 4 | 14,080 `MUL` | PASS |
| RV32IM 快速 | `1/1/1` | `rv32im/ilp32` | 433,599 / 433,599 / 433,599 | 433,605 | 4 | 14,080 `MUL` | PASS |

以未分段总周期平均值计算，RV32IM 迭代相对 RV32I 的软件多项式乘法时间为 **3.11×**，快速乘法为 **6.55×**；这是同一 CPU 存储系统上的**软件 baseline 对照**，不是相对 PQC 硬件加速器的加速比。迭代与快速配置使用同一 RV32IM 镜像，区别只在 CPU `FAST_MUL` 参数。RV32I 的执行时间随输入变化，主要来自 `__mulsi3` 移位加法软件例程的数据相关路径；结论应报告 8 case 分布，不应只挑选单个样本。

分段平均（profiled run，包含该次分段时间戳开销）如下：

| 配置 | Prepare | NTT(A) | NTT(B) | BaseMul | INTT/scale | Canonicalize | 分段合计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| RV32I | 6,543 | 763,907 | 763,911 | 412,097.9 | 855,464 | 36,896 | 2,838,818.9 |
| RV32IM 迭代 | 6,543 | 216,981 | 216,981 | 101,885 | 328,160 | 41,775 | 912,325 |
| RV32IM 快速 | 6,543 | 108,181 | 108,181 | 36,605 | 149,728 | 24,367 | 433,605 |

三组均观测到栈指针处于预留范围 `0x37f0..0x3ff0`；最低值分别为 `0x3f20`（RV32I，栈使用 208 B）和 `0x3f50`（两种 RV32IM，栈使用 160 B）。RV32IM 反汇编在 `sw_ntt`、`sw_basemul` 和 `sw_invntt` 中均存在实际 `MUL`；RV32I 窗口内 M 指令为 0。所有地址请求、trap、事件顺序、输入/输出系数均通过检查。

固件构建统计：RV32I 镜像 5,024 B，RV32IM 镜像 3,468 B；两者静态数据区 2,560 B，链接器为栈保留 2 KiB。镜像、编译器、源码/镜像/libgcc SHA256 记录在 [CPU 构建清单](../results/cpu_baseline/cpu_baseline_build_manifest.json)；反汇编、ELF、map 和详细构建日志仍在 [build/cpu_baseline/firmware](../build/cpu_baseline/firmware)（本地生成目录）。

当前 CPU 仿真使用 XSim 的 100 MHz 等效时钟和真实 PicoRV32 AXI/XPM RAM 通路；CPU-only PYNQ-Z2 实板烧录仍未执行。三组 CPU-only top 已在相同 PYNQ-Z2 器件、约束和 100 MHz 时钟下完成综合/布局布线，并导出独立 bitstream。不能把本节周期直接和原加速器 `Core=4789` 周期混称为同一计时边界。

### CPU-only Vivado 实现对照

三组均为 `cpu_benchmark_pynqz2_top`、`xc7z020clg400-1`、16 KiB BRAM、无 VIO，只有 PicoRV32 的 `MUL/FAST_MUL/DIV` 参数和对应固件镜像不同。报告来自 Vivado 2024.2 fully routed design；功耗为无活动文件的 vectorless 估计，不能替代实测功耗。

| 配置 | Slice LUTs | Slice FFs | BRAM36 | DSP | WNS (ns) | WHS (ns) | DRC errors / warnings | BIT |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| RV32I | 1,221 | 1,132 | 4 | 0 | +2.416 | +0.073 | 0 / 2 | [bit](../release/cpu_baseline_rv32i/cpu_baseline_rv32i.bit) |
| RV32IM 迭代 | 1,828 | 1,611 | 4 | 0 | +1.954 | +0.128 | 0 / 2 | [bit](../release/cpu_baseline_rv32im_iterative/cpu_baseline_rv32im_iterative.bit) |
| RV32IM 快速 | 1,720 | 1,393 | 4 | 4 | +2.136 | +0.047 | 0 / 3 | [bit](../release/cpu_baseline_rv32im_fast/cpu_baseline_rv32im_fast.bit) |

相对 RV32I，迭代 M 扩展增加 607 LUT、479 FF；快速 M 扩展增加 499 LUT、261 FF 和 4 DSP。三组均满足 100 MHz setup/hold 约束；快速乘法的速度收益应与额外 DSP 及软件算法周期一起报告。原始报告在各配置的 `results/cpu_baseline/<config>/` 下，复现入口为 `scripts/cpu_baseline/implement.tcl`。

## 1. 阶段 2：RV32IM 迭代乘除法

记录日期：2026-09-22。本阶段启用 PicoRV32 已有的迭代乘法器和除法器，完成 M 指令定向验证、原加速路径回归及 Vivado 实现。PicoRV32 内部、加速器 RTL/HLS、固件镜像和原有周期断言均未改动；4 个板级/系统/TB 文件只增加 CPU 参数透传，见 [源码变更清单](source_changes.csv)。

### 构建身份与比较条件

| 条目 | RV32I 基线 | RV32IM 迭代配置 |
|---|---|---|
| 配置 ID | `rv32i` | `rv32im_iterative` |
| 源码版本 | `4753221fdaed34fa52b4580e0003bec6ad33ab2c` | 基于左侧提交，分支 `rv32im-iterative`；构建输入以 [SHA256 清单](../results/rv32im_iterative/build_inputs.csv) 为准 |
| Vivado / XSim | 2024.2，Build 5239630 | 同左 |
| FPGA | PYNQ-Z2，`xc7z020clg400-1` | 同左 |
| 输入 / CPU / 加速核时钟 | 125 / 100 / 100 MHz | 同左 |
| `ENABLE_MUL / ENABLE_FAST_MUL / ENABLE_DIV` | `0 / 0 / 0` | `1 / 0 / 1` |
| 迭代乘法内部参数 | 不适用 | 原始默认 `STEPS_AT_ONCE=1`、`CARRY_CHAIN=4` |
| 系统程序与数据 RAM | 4 KiB | 同左 |
| VIO / debug hub | 包含 | 包含 |
| 固件 | `firmware/images/transfer_both_unroll4.mem` | 同一镜像 |
| 固件 ISA / ABI / 优化 | RV32I / ILP32 / `-O2` | 同左；本轮没有编译 RV32IM C 应用 |
| 综合 / 实现策略 | `Flow_PerfOptimized_high` / `Performance_Explore` | 同左 |
| XPR | [原工程](../vivado/project/mlkem_pynqz2.xpr) | [迭代工程](../vivado/project_rv32im_iterative/mlkem_pynqz2.xpr) |
| 实现报告 | [历史报告](../results/rv32i_baseline/) | [本轮报告](../results/rv32im_iterative/) |
| BIT / LTX | [原产物](../release/) | [迭代产物](../release/rv32im_iterative/) |

固件 SHA256：

```text
F813ECDE8CD06C9D3644AAFAF7B34E0F4ACDBE9D37DC5E7AEC9A5720FCFBBB0E
```

原 transfer 固件的 `.text` 中 M 指令数为 0。此次复用它用于兼容性回归；它没有执行软件 NTT，因此不能由其周期推导软件多项式乘法速度。加速核仍为已有 HLS 生成 RTL 快照，未重新进行 HLS 综合。

### M 指令正确性与周期

CPU 测试实际执行 `LUI/ADDI → RDCYCLE → M 指令 → RDCYCLE → SW` 指令流，经 CPU 译码与寄存器文件执行，再用 64 位行为参考检查结果。测试 ROM 由 TB 生成，约 160 KiB，仅存在于仿真中；板级 4 KiB RAM 没有扩大。完整方法见 [CPU 测试说明](../tb/cpu/README.md)。

| 覆盖项 | 实测结果 |
|---|---|
| 每种指令的边界输入 | 16 个边界值的笛卡尔积，共 256 对 |
| 每种指令的随机输入 | 256 对，xorshift32，固定种子 `0x6d6c6b65` |
| 指令种类 / 每种样本 / 总检查数 | 8 / 512 / 4096 |
| PCPI 完成次数 | 4096 |
| 算术错误 / 非预期 trap | 0 / 0 |
| 关键边界 | 有符号/无符号/混合符号高位乘法、除零、`INT_MIN / -1`、余数符号与溢出 |
| 空 `rdcycle; rdcycle` 区间 | 4 周期 |
| 测试整体运行周期 | 348187，含输入加载、计时、结果输出等；不是算法延迟 |

以下单位均为周期，各格是 **最小 / 平均 / 最大**，每条指令 512 个样本。

| 指令 | 原始 RDCYCLE 区间 | 减去空区间后的增量 | PCPI 服务区间 |
|---|---:|---:|---:|
| MUL | 44 / 44 / 44 | 40 / 40 / 40 | 36 / 36 / 36 |
| MULH | 76 / 76 / 76 | 72 / 72 / 72 | 68 / 68 / 68 |
| MULHSU | 76 / 76 / 76 | 72 / 72 / 72 | 68 / 68 / 68 |
| MULHU | 76 / 76 / 76 | 72 / 72 / 72 | 68 / 68 / 68 |
| DIV | 44 / 44 / 44 | 40 / 40 / 40 | 36 / 36 / 36 |
| DIVU | 44 / 44 / 44 | 40 / 40 / 40 | 36 / 36 / 36 |
| REM | 44 / 44 / 44 | 40 / 40 / 40 | 36 / 36 / 36 |
| REMU | 44 / 44 / 44 | 40 / 40 / 40 | 36 / 36 / 36 |

原始区间为两次 `rdcycle` 的差；增量为插入该条 M 指令相对空区间增加的 CPU 周期，仍包含该存储模型下的取指/译码开销。PCPI 区间为首次采样 `pcpi_valid` 到采样 `pcpi_valid && pcpi_int_ready` 的时钟边沿距离，不含此前的 CPU 取指/译码。

**此测试使用原生存储口 `mem_ready=mem_valid` 和组合 ROM 读，不是板级 AXI/BRAM 存储系统。** 本轮未测板级完整存储路径上的 M 指令应用性能。以上 512 个样本周期一致，仅说明这些样本和配置的观测结果，不构成完整 ISA 合规或恒定时间安全证明。

证据：[CPU 原始日志](../results/rv32im_iterative/sim_cpu.txt)、[周期 CSV](../results/rv32im_iterative/instruction_cycles.csv)。通过标记：`RV32IM_ISA_PASS tests=4096 pcpi=4096 cycles=348187 fast_mul=0`。

### 原加速路径兼容性回归

| 指标 | RV32I 周期 | RV32IM 迭代周期 | 迭代版时间 @100 MHz | 含义 |
|---|---:|---:|---:|---|
| Write | 5873 | 5873 | 58.73 µs | 本地输入写入加速器 |
| Start | 19 | 19 | 0.19 µs | 发起运算 |
| Poll | 4827 | 4827 | 48.27 µs | CPU 轮询等待完成 |
| Read | 3233 | 3233 | 32.33 µs | 结果读回本地 RAM |
| Call | 13952 | 13952 | 139.52 µs | Write + Start + Poll + Read |
| Core | 4789 | 4789 | 47.89 µs | 硬件核内部计算，与 Poll 重叠 |
| Polls（次数） | 185 | 185 | 不适用 | 轮询次数，非时钟周期 |
| RDCYCLE 校准 | 4 | 4 | 0.04 µs | 单独记录，不擅自从各段扣除 |

两个配置的 VIO 测试均进行 3 次复位试验，每次以独立直接卷积参考检查 256 个系数，结果及周期断言全部通过。RV32I 默认参数在本轮也重新回归。Call 不含输入生成和结果校验；Core 与 Poll 重叠，不能把 Core 再加到 Call。

本表 Core 采用板级 wrapper 的 `cycle_count` 口径：从接受启动后开始累计 `busy` 周期，直至观察到 `ap_done`。独立核心 TB 从撤销 `ap_start` 后开始计数，其日志为 4788 周期；两者计时起点相差一拍，不应混用。

证据：[RV32I 默认回归](../results/rv32i_baseline/sim_1_current.txt)、[RV32IM VIO 回归](../results/rv32im_iterative/sim_1.txt)，各细分周期由 [TB 原有断言](../tb/board/tb_pynqz2_profile_vio.sv) 检查。

### 布线后资源

完整系统包含 CPU、AXI/BRAM、加速器、VIO、debug hub、时钟和复位逻辑。百分比增量以 RV32I 用量为分母。

| 资源 | RV32I | RV32IM 迭代 | 绝对增量 | 相对增量 | 迭代版器件占用率 |
|---|---:|---:|---:|---:|---:|
| LUT | 3956 | 4660 | +704 | +17.80% | 8.76% |
| FF | 5053 | 5534 | +481 | +9.52% | 5.20% |
| DSP48E1 | 1 | 1 | 0 | 0% | 0.45% |
| RAMB36 | 4 | 4 | 0 | 0% | 2.86% |
| RAMB18 | 5 | 5 | 0 | 0% | 1.79% |
| BRAM36 等效 | 6.5 | 6.5 | 0 | 0% | 4.64% |

下面是迭代版本的层次资源定位，父项包含子项，不能将所有行累加。LUT 合并和跨层优化也可能造成层次之和与总量的小幅差异。

| 迭代版本层次 | LUT | FF | RAMB36 | RAMB18 | DSP |
|---|---:|---:|---:|---:|---:|
| CPU + AXI adapter（`system_i/cpu`） | 1973 | 1016 | 0 | 0 | 0 |
| └ 迭代乘法器 `pcpi_mul` | 339 | 256 | 0 | 0 | 0 |
| └ 除法器 `pcpi_div` | 355 | 201 | 0 | 0 | 0 |
| 加速器 + AXI wrapper（`system_i/accel`） | 2004 | 1741 | 3 | 5 | 1 |
| └ 加速器核心 `core` | 1731 | 1608 | 3 | 2 | 1 |

此次增加的是完整 M 扩展，含乘法和除法；全系统 +704 LUT 不能全部称为“乘法器面积”。该差值也包含综合/布局优化差异。证据：[基线资源](../results/rv32i_baseline/utilization_routed.rpt)、[迭代资源](../results/rv32im_iterative/utilization_routed.rpt)、[层次资源](../results/rv32im_iterative/utilization_hierarchical.rpt)。

### 布线后时序与 DRC

| 指标 | RV32I | RV32IM 迭代 |
|---|---:|---:|
| 工作频率 | 100 MHz | 100 MHz |
| WNS / TNS | +1.027 / 0.000 ns | +1.367 / 0.000 ns |
| WHS / THS | +0.023 / 0.000 ns | +0.034 / 0.000 ns |
| WPWS / TPWS | +2.000 / 0.000 ns | +2.000 / 0.000 ns |
| Setup / hold / pulse-width 失败端点 | 0 / 0 / 0 | 0 / 0 / 0 |
| 无时钟寄存器 / 未约束内部端点 | 0 / 0 | 0 / 0 |
| Bus-skew 最差余量（4 条约束） | +9.158 ns | +9.220 ns |
| DRC Error / Warning | 0 / 23 | 0 / 20 |

两次实现均满足 100 MHz 约束；WNS 是约束下的余量，本轮没有扫频测 Fmax。原 XDC 对 BTN0 与四个 LED 设置了时序例外。迭代版 DRC 警告包括原加速核 DSP 的 MREG 建议、调试逻辑 LUT/布线检查以及纯 PL 设计未实例化 PS7；具体以 [DRC 报告](../results/rv32im_iterative/drc_routed.rpt) 为准。

证据：[时序](../results/rv32im_iterative/timing_routed.rpt)、[bus-skew](../results/rv32im_iterative/bus_skew_routed.rpt)、[历史验证记录](VALIDATION.md)。

### 检查完成状态与产物

| 检查 | 状态 | 证据 |
|---|---|---|
| M 指令仿真 `cpu` | PASS，4096 项 | [日志](../results/rv32im_iterative/sim_cpu.txt) |
| 加速核 `core` | PASS，3 组 | [日志](../results/rv32im_iterative/sim_core.txt) |
| AXI/BRAM 协议 `protocol` | PASS | [日志](../results/rv32im_iterative/sim_protocol.txt) |
| 板级 RTL `board` | PASS | [日志](../results/rv32im_iterative/sim_board.txt) |
| 板级 VIO RTL `vio` | PASS，3 次复位 | [日志](../results/rv32im_iterative/sim_1.txt) |
| 默认 RV32I 参数回归 | PASS，3 次复位 | [日志](../results/rv32i_baseline/sim_1_current.txt) |
| 综合 / 布局布线 / BIT 导出 | PASS | [综合参数日志](../results/rv32im_iterative/synthesis.txt)、上列 Routed 报告 |
| 实体板烧录 / VIO 实板读回 | 未执行 | 按本轮要求仅完成仿真和实现 |
| 软件多项式乘法 / 软硬件加速比 | 待阶段 3 | 尚无软件 NTT 基线 |

| 迭代版本产物 | SHA256 |
|---|---|
| `release/rv32im_iterative/mlkem_pynqz2.bit` | `263afef9000b0e23d1edf3f02b1694ee6f5e806ada8a6e39f7b089b6a64208b4` |
| `release/rv32im_iterative/mlkem_pynqz2.ltx` | `f69dfb0b22f55b7a9ecd2f0685c130033a0df463531c78f295a298b031ffda03` |

结果与产物关联记录：[release_sha256.txt](../results/rv32im_iterative/release_sha256.txt)。结果目录的 [SHA256SUMS](../results/rv32im_iterative/SHA256SUMS) 校验原始证据文件，`build_inputs.csv` 校验源码、TB、约束、镜像、XPR/XCI 和构建 Tcl。

### 复现

在仓库根目录、Vivado 2024.2 环境运行以下 PowerShell 命令。`implement` 自动执行全部五组仿真后综合与实现；完成后归档结果，不会烧录开发板。

```powershell
vivado -mode batch -source scripts/run.tcl -tclargs implement firmware/images rv32im_iterative
./scripts/update_release_checksums.ps1 -CpuConfig rv32im_iterative
./scripts/collect_rv32im_measurements.ps1
./scripts/verify_sources.ps1
```

仅复现指令测试：

```text
vivado -mode batch -source scripts/run.tcl -tclargs cpu firmware/images rv32im_iterative
```

Tcl 会重新创建对应配置的工程。正式收集时应先完成整套 `implement`，确保仿真、实现和产物属于同一组输入；不要在只重跑部分仿真后将旧实现当成新结果。当前表是本次固定记录，重新实现导致数据变化时需同步更新本表并保留旧记录。更多入口见 [BUILD.md](BUILD.md)。

## 2. 后续应用性能表（待测）

应用比较必须使用相同多项式输入、算法语义和正确性检查，注明编译选项、实际 M 指令使用、内存布局及计时范围。当前 `Call=13952` 可作为本轮硬件调用参考；后续若修改固件、RAM 或接口，应重新测量，不能直接沿用。

| 配置 | 软件 NTT 周期 | 软件 BaseMul 周期 | 软件 INTT 周期 | 软件完整多项式乘法周期 | 硬件 Call 周期 | 端到端加速比 |
|---|---|---|---|---|---|---|
| RV32I 软件基线 | 待测 | 待测 | 待测 | 待测 | 待同口径复测 | 待测 |
| RV32IM 迭代软件基线 | 待测 | 待测 | 待测 | 待测 | 待同口径复测 | 待测 |
| RV32IM 快速乘法（后续可选） | 待测 | 待测 | 待测 | 待测 | 待同口径复测 | 待测 |

端到端加速比定义为 `同配置软件完整多项式乘法周期 / 硬件 Call 周期`，计时起止均为输入已在本地 RAM 就绪至结果写回本地 RAM。软件完整流程必须包含与硬件相同的归一化/模约减；应与分阶段计时分开测量，避免重复计时开销。核内周期比若单独展示，须明确不含传输。
