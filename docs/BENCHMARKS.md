# 性能与资源数据表

更新时间：2026-09-27。表中只列已完成且仍有源码/日志证据的结果。100 MHz 时间换算仅用于
仿真周期的直观展示；新 HLS 估算不等同于端到端系统性能。

## K4 CPU＋Keccak完整官方RTL对照（145/145）

2026-09-27完成19批，145条官方记录唯一覆盖、每批最终PASS。同RV32IM-fast、
128 KiB RAM / 32 KiB栈；完整API计入打包、上下文切换、MMIO、等待、读回和CPU清零。
加速比为同组CPU-only周期总和除以加速周期总和，保留两次rdcycle的原始计时区间。

| 操作 | 记录数 | CPU-only cycles | CPU+Keccak cycles | 加速比 |
|---|---:|---:|---:|---:|
| KeyGen | 25 | 329,300,132 | 78,355,267 | 4.203× |
| Encaps | 50 | 700,468,926 | 192,648,902 | 3.636× |
| Decaps | 20 | 331,730,912 | 92,092,840 | 3.602× |
| 从种子重建私钥并Decaps | 10 | 295,059,990 | 77,103,920 | 3.827× |
| 私钥检查（含有效/无效） | 20 | 37,586,170 | 1,504,350 | 24.984× |
| 公钥检查（含有效/无效） | 20 | 5,148,230 | 5,148,230 | 1.000× |
| 当前测试集合计 | 145 | **1,699,294,360** | **446,853,509** | **3.803×** |

合计比值取决于官方测试集操作组合，不代表任意应用负载的固定加速比。3,188次真实启动/完成
与预期一致（3,120 HASH＋68 SQUEEZE）；公钥检查不调用硬件，周期与CPU-only相同。
硬件busy总计1,980,263 cycles，CPU缓冲写/读257,851/435,632个32-bit事务（含上下文）。
其余444,873,246 API cycles还包含CPU算法和接口处理，不能全部称为搬运或轮询。
全TB周期合计495,540,106（含启动、测试数据传输和校验），不用于替换API对照口径。
最大观测栈24,384 B，未超过32 KiB预留；不是对所有输入的最坏栈证明。
19批运行时长合计7,056.986 s（约1小时58分，含编译/展开），不是芯片执行时间。

[逐例CSV、全量汇总和19批原始日志](../results/keccak_cpu/kat/summary.md)均已保存。
这是RTL周期对照；完整系统OOC已测：资源足够、100 MHz内部setup −1.367 ns，尚未完成板级时序或实板性能验证。
完整运行前冻结快照保留在`E:/hls/k4kat/`，HLS生成文件不进入Git，也不清理该证据目录。

## K4完整系统OOC物理对照

相同128 KiB RAM、RV32IM-fast、100 MHz约束；内部指寄存器/BRAM之间的路径。

| 系统 | LUT | FF | BRAM36等效tile | DSP | 内部setup | 内部hold |
|---|---:|---:|---:|---:|---:|---:|
| CPU-only | 1,719 | 1,388 | 32 | 4 | +1.452 ns | +0.051 ns |
| CPU+Keccak | 19,084 | 16,970 | 34.5 | 4 | **−1.367 ns** | +0.050 ns |

资源满足XC7Z020容量；加速组100 MHz尚未收敛。关键路径为地址译码/adapter ready反馈至
程序RAM地址，布线延迟占76.9%。接口边界resetn未固定物理位置，全路径hold不用于板级签核。
两组布线完整、内部端点均有约束、pulse width通过；实板与完整板级时序尚未验证。
[完整系统实现报告](../results/keccak_cpu/system_impl/20260927_194022/summary.md)；大体积DCP和冻结输入保留在`E:/hls/k4sys/20260927_194022/`。

## K4 CPU＋Keccak 接口闭环

10次组件RTL调用、216个结果字、10次HLS启动/完成全部通过；四种模式、上下文和错误返回已验证。
CPU使用RV32IM-fast、128KiB RAM/32KiB栈，固件4888B。调用区间总计72,287cycles，
硬件busy共4,070cycles；完整TB326,618cycles。两者计时口径见
[逐调用表和日志](../results/keccak_cpu/smoke/README.md)。
这不是完整K4官方加速KAT，也没有同形状CPU-only微基准，不能计算系统加速比。

## K4 Keccak HLS 首轮独立验证

109笔本地FIPS202差分事务，两配置C/RTL COSIM通过；不计入官方KAT覆盖。

| 指标 | 字节基线 io0 | 打包优化 io1 |
|---|---:|---:|
| COSIM全TB周期（含生成的AXI-Lite驱动） | 1,314,553 | 75,280 |
| HLS LUT / FF估算 | 14,612 / 17,008 | 15,244 / 15,385 |
| HLS BRAM18K / DSP估算 | 2 / 0 | 2 / 0 |
| HLS时钟估算 | 8.622 ns | 8.895 ns |
| OOC布局布线LUT / FF | 未执行 | 16,885 / 15,320 |
| OOC WNS / WHS（10 ns约束） | 未执行 | +0.279 / +0.098 ns |

相同测试序列周期比17.462×，不是K4系统加速比。OOC外部CPU/BRAM未计入，
外部I/O时序与系统时钟树待集成。详见[完整口径及原始证据](../results/hls/mlkem1024_keccak/summary.md)。

## ML-KEM-512 官方 PicoRV32 回归

| 配置 | 通过记录 | 算法区间总周期 | 动态 M 指令 | 最大观测栈 |
|---|---:|---:|---:|---:|
| RV32I | 145/145 | 1,400,566,832 | 0 | 12,928 B |
| RV32IM 迭代 | 145/145 | 812,132,449 | 3,486,720 | 12,928 B |
| RV32IM 快速 | 145/145 | 692,273,249 | 3,486,720 | 12,928 B |

证据：[`results/official_baseline/mlkem512/summary.md`](../results/official_baseline/mlkem512/summary.md)、
[`summary.json`](../results/official_baseline/mlkem512/summary.json) 和逐条结果
[`cases.csv`](../results/official_baseline/mlkem512/cases.csv)。三种 CPU 使用相同的
ML-KEM-512 固定版本 145 条记录；这不是三个参数集各 145 条。

## 扩展参数集 CPU-only RTL 正确性与基本指标

| 参数集 / CPU | 官方记录 | 算法区间总周期 | RAM / 栈预留 | 最大观测栈 |
|---|---:|---:|---|---:|
| 768 / RV32IM-fast | 145/145 PASS | 1,112,525,793 | 128 / 32 KiB | 18,432 B |
| 1024 / RV32IM-fast | 145/145 PASS | 1,699,294,360 | 128 / 32 KiB | 24,464 B |

[768逐操作表和证据](../results/official_baseline/mlkem768/rv32im_fast/summary.md)。
768输入/输出共核对215,360/146,560 B；1024输入/输出共核对287,360/199,360 B。
768全程1,147,835,590 cycles，1024全程1,747,426,461 cycles，包含启动和传输，不代替算法区间。
128 KiB为本次验证配置，未证明是最小容量；32 KiB为栈预留，18,432/24,464 B为测试集观测值。
512的64/16 KiB口径不同，不能把所有差异归因于参数规模。上表两组均为纯CPU；K4加速RTL结果另列于本文首表，K3硬件扩展、
K4系统时序优化和实板仍待完成。

## 主机端官方参考回归

| 参数集 | 记录数 | 结果 |
|---|---:|---|
| ML-KEM-512 | 145 | PASS |
| ML-KEM-768 | 145 | PASS |
| ML-KEM-1024 | 145 | PASS |
| 合计 | 435 | PASS |

证据：[`results/official_reference/`](../results/official_reference/)；向量来源：
[`vectors/official_kat/acvp/SOURCES.md`](../vectors/official_kat/acvp/SOURCES.md)。

## CPU-only 实现结果

三组 CPU-only 工程均已有 Vivado 2024.2 实现结果，报告按配置保存：

| 配置 | Vivado 工程 | BIT | 报告目录 |
|---|---|---|---|
| RV32I | [`vivado/cpu_baseline_rv32i/cpu_baseline.xpr`](../vivado/cpu_baseline_rv32i/cpu_baseline.xpr) | [`release/cpu_baseline_rv32i/cpu_baseline_rv32i.bit`](../release/cpu_baseline_rv32i/cpu_baseline_rv32i.bit) | [`results/cpu_baseline/rv32i/`](../results/cpu_baseline/rv32i/) |
| RV32IM 迭代 | [`vivado/cpu_baseline_rv32im_iterative/cpu_baseline.xpr`](../vivado/cpu_baseline_rv32im_iterative/cpu_baseline.xpr) | [`release/cpu_baseline_rv32im_iterative/cpu_baseline_rv32im_iterative.bit`](../release/cpu_baseline_rv32im_iterative/cpu_baseline_rv32im_iterative.bit) | [`results/cpu_baseline/rv32im_iterative/`](../results/cpu_baseline/rv32im_iterative/) |
| RV32IM 快速 | [`vivado/cpu_baseline_rv32im_fast/cpu_baseline.xpr`](../vivado/cpu_baseline_rv32im_fast/cpu_baseline.xpr) | [`release/cpu_baseline_rv32im_fast/cpu_baseline_rv32im_fast.bit`](../release/cpu_baseline_rv32im_fast/cpu_baseline_rv32im_fast.bit) | [`results/cpu_baseline/rv32im_fast/`](../results/cpu_baseline/rv32im_fast/) |

`results/cpu_baseline/cpu_benchmark_summary.json` 和 `cpu_benchmark_rows.csv` 是资源、
时序、周期和配置的结构化汇总。实现报告只描述 CPU-only 设计，不能用作新 HLS 接入后的
系统资源或加速比。

## RV32IM-fast 阶段 profiling

快速乘法配置的 145 条记录、19 个批次均通过。主要 API 的 Keccak 占比约 71%–81%，
多项式算术占比约 13%–21%；阶段独占周期之和与 API 总周期逐条相等。完整分析见
[`docs/MLKEM512_PROFILE.md`](MLKEM512_PROFILE.md)。

## RV32IM-fast + CPU/PQC 官方 ML-KEM-512 KAT

加速版使用与 CPU-only 完全相同的 145 条固定 ACVP 记录、RV32IM-fast 固件、64 KiB
RAM 和 100 MHz 仿真时钟；19 个独立批次全部通过，输入/输出逐字节核对，且每条记录的
MMIO 计数与 adapter 协议一致。`speedup` 定义为 CPU-only API 周期 / CPU+PQC API 周期，
小于 1 表示当前系统变慢。

| 操作 | 记录 | CPU-only 总周期 | CPU+PQC 总周期 | 端到端 speedup | 加速核心周期占比 | 搬入/读回占比 |
|---|---:|---:|---:|---:|---:|---:|
| KeyGen | 25 | 131,735,099 | 132,452,949 | 0.9946× | 0.0051% | 1.8199% |
| Encapsulation | 50 | 279,054,831 | 281,208,381 | 0.9923× | 0.0073% | 2.5716% |
| Decapsulation | 20 | 138,754,785 | 139,903,345 | 0.9918× | 0.0078% | 2.7567% |
| DecapsulationSeed | 10 | 121,320,854 | 122,182,274 | 0.9929× | 0.0067% | 2.3675% |
| 合计 | 145 | 692,273,249 | 697,154,629 | **0.9930×** | **0.0066%** | **2.3512%** |

当前结果说明 K=2 BaseMul 核心功能和软件接入路径正确，但端到端系统尚未获得性能收益：
核心只有 46,240 cycles，而 CPU API 总周期增加 4,881,380 cycles；搬入、读回和驱动/轮询
开销大于核心节省的时间。密钥检查操作不调用加速器，因此保持 1.0000×。这组数据是
Vivado 2024.2/XSim 的 RTL 仿真证据，不是实板测量或正式认证。逐例 CSV、JSON、批次日志和
输入/期望向量见 [`results/accelerator_cpu/kat/`](../results/accelerator_cpu/kat/)。

## 新 HLS K=2 BaseMul

| 指标 | 当前结果 |
|---|---:|
| C 仿真 | 103/103 |
| Pipeline II | 1 |
| HLS 核心估算延迟 | 137 cycles |
| HLS 估算 Fmax | 150.83 MHz |
| DSP / LUT / FF / BRAM | 12 / 310 / 599 / 0 |

证据：[`results/accelerator_interface/hls_synthesis/`](../results/accelerator_interface/hls_synthesis/)、
[`hls/mlkem512_basemul_k2/ip/`](../hls/mlkem512_basemul_k2/ip/)。HLS 数字只覆盖核心；
独立 MMIO/BRAM 验证的额外数据如下：

| 独立硬件指标 | 结果 |
|---|---:|
| RTL 核心周期/组 | 136 cycles |
| 输入写事务/组 | 640 |
| 结果读事务/组 | 128 |
| 首次写入到最末结果字读请求被接受（含首尾） | 1800 cycles |
| RTL 回归 | 3 组、768 个系数逐项 PASS |
| 板级 BIST RTL | 2 次 PASS、256 个结果字检查、1 次故障注入检测 |
| Vivado WNS / WHS | 0.732 ns / 0.129 ns |
| BRAM / DSP 原语 | 8 / 12 |
| LUT / FF | 566 / 386 |
| BRAM 细分 | 7 × RAMB18 + 1 × RAMB36（4.5 tiles） |

证据：[`results/accelerator_interface/rtl_sim/`](../results/accelerator_interface/rtl_sim/)、
[`results/accelerator_interface/vivado_impl/`](../results/accelerator_interface/vivado_impl/)。
1800 cycles 来自当前 TB 的请求间隔，未包含最末读响应与调用方检查，不是 CPU 驱动开销。
资源包含 BIST 控制器/ROM；未用到的诊断计数等逻辑可能在独立顶层综合中被裁剪，不能
直接当成 CPU 接入后的完整 adapter 资源。CPU API 和完整 KEM 周期仍待系统集成后测量。

## 后续统一计时口径

### K=4首批代表用例历史记录（已被上方全量统计补齐）

固定同RV32IM-fast、128 KiB RAM / 32 KiB栈，使用原官方索引0、1、115；
完整API原始rdcycle区间包括provider及MMIO成本，无算法阶段插桩。

| 官方索引 / API | CPU-only cycles | CPU+Keccak cycles | 加速比 | HASH / SQUEEZE |
|---|---:|---:|---:|---:|
| 0 / KeyGen | 13,046,698 | 3,120,949 | 4.180× | 26 / 0 |
| 1 / Encaps | 13,908,293 | 3,841,529 | 3.621× | 27 / 0 |
| 115 / 隐式拒绝Decaps，含续取 | 17,088,709 | 4,658,623 | 3.668× | 28 / 4 |

3/3逐字节官方输出及返回值通过；85次真实启动/完成与命令、搬运字数全部吻合。
硬件busy共51,913 cycles，不能将其余API周期全算作搬运或等待。
完整仿真TB最大观测栈24,384 B；首批墙钟185.4 s，不是芯片执行时间。
后续142条也已通过；全量结果见本文首表及[独立汇总](../results/keccak_cpu/kat/summary.md)。
此处保留首批历史数据，不与全量分组加速比混用。

新增 [RV32IM-fast＋加速器接口验证](MLKEM512_CPU_ACCEL_SMOKE.md)：3 组输入各 48,632
调用周期、136 核心周期，768 个系数通过。官方 145 条 KAT 的完整 CPU/PQC 对照已完成，
但当前端到端结果为 0.9930×，后续优化目标应优先降低搬运和轮询开销。

CPU-only 与 CPU+PQC 硬件必须同时记录：

1. CPU API 周期；
2. 输入写入、启动、等待、输出读回和清零周期；
3. HLS/RTL 核心周期；
4. LUT、FF、DSP、BRAM、WNS/WHS 和功耗估计；
5. 官方输入/输出逐字节结果。

只有在相同官方记录、相同频率和相同计时边界下，才计算端到端加速比。
