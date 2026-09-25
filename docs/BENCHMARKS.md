# 性能与资源数据表

更新时间：2026-09-25。表中只列已完成且仍有源码/日志证据的结果。100 MHz 时间换算仅用于
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

## 新 HLS K=2 BaseMul

| 指标 | 当前结果 |
|---|---:|
| C 仿真 | 103/103 |
| Pipeline II | 1 |
| HLS 核心估算延迟 | 137 cycles |
| HLS 估算 Fmax | 150.83 MHz |
| DSP / LUT / FF / BRAM | 12 / 310 / 599 / 0 |

证据：[`results/accelerator_interface/hls_synthesis/`](../results/accelerator_interface/hls_synthesis/)、
[`hls/mlkem512_basemul_k2/ip/`](../hls/mlkem512_basemul_k2/ip/)。这些数字只覆盖 HLS 核心；
AXI/BRAM 搬运、CPU API 和完整 KEM 仍待新 Vivado 顶层完成后单独测量。

## 后续统一计时口径

CPU-only 与 CPU+PQC 硬件必须同时记录：

1. CPU API 周期；
2. 输入写入、启动、等待、输出读回和清零周期；
3. HLS/RTL 核心周期；
4. LUT、FF、DSP、BRAM、WNS/WHS 和功耗估计；
5. 官方输入/输出逐字节结果。

只有在相同官方记录、相同频率和相同计时边界下，才计算端到端加速比。
