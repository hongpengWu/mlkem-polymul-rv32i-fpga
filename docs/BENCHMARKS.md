# 性能与资源数据表

更新时间：2026-09-26。表中只列已完成且仍有源码/日志证据的结果。100 MHz 时间换算仅用于
仿真周期的直观展示；新 HLS 估算不等同于端到端系统性能。

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
| 1024 / RV32IM-fast | 19个顺序批次运行中 | 待汇总 | 128 / 32 KiB | 待测 |

[768逐操作表和证据](../results/official_baseline/mlkem768/rv32im_fast/summary.md)。
768输入/输出共核对215,360/146,560 B；全程1,147,835,590 cycles包含启动和传输，
不可代替上表算法区间。128 KiB为本次验证配置，未证明是最小容量；32 KiB为栈预留，
18,432 B为测试集观测值。512的64/16 KiB口径不同，不能把所有差异归因于参数规模。
两组均为纯CPU；K3/K4加速器、布局布线和实板仍待验证。

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
