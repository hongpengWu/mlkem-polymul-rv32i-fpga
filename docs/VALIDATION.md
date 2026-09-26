# 验证记录

更新时间：2026-09-26。本文只记录当前仍在仓库中的验证入口和证据；旧完整加速器的
板级仿真、实现报告和 bitstream 已随旧主线删除。

## 当前结果

| 项目 | 状态 | 证据 |
|---|---|---|
| CPU-only 多项式 baseline | PASS，RV32I/RV32IM-iterative/RV32IM-fast 各 8 组、4096 项检查 | [`results/cpu_baseline/`](../results/cpu_baseline/) |
| ML-KEM-512 官方 PicoRV32 回归 | PASS，三种 CPU 各 145/145 | [`results/official_baseline/mlkem512/`](../results/official_baseline/mlkem512/) |
| ML-KEM-768 官方 PicoRV32 回归 | PASS，RV32IM-fast 145/145，128 KiB RAM/32 KiB栈 | [768汇总](../results/official_baseline/mlkem768/rv32im_fast/summary.md) |
| ML-KEM-1024 官方 PicoRV32 回归 | PASS，RV32IM-fast 145/145，128 KiB RAM/32 KiB栈 | [1024汇总](../results/official_baseline/mlkem1024/rv32im_fast/summary.md) |
| 主机端 FIPS 203/ACVP | PASS，512/768/1024 合计 435 条 | [`results/official_reference/`](../results/official_reference/) |
| KeyGen 官方 tcId=1 | PASS，三种 CPU | [`results/official_baseline/keygen512_tc1/`](../results/official_baseline/keygen512_tc1/) |
| RV32IM 指令配置 | PASS，迭代和快速乘法配置均在软件回归中使用 | [`tb/cpu/`](../tb/cpu/) |
| 新 HLS C 仿真 | PASS，103/103 | [`results/accelerator_interface/basemul_k2_csim.txt`](../results/accelerator_interface/basemul_k2_csim.txt) |
| 新 HLS 2024.2 综合 | PASS，II=1，估算 137 cycles、150.83 MHz | [`results/accelerator_interface/hls_synthesis/`](../results/accelerator_interface/hls_synthesis/) |
| 新 HLS MMIO/BRAM Vivado 顶层 | PASS，3 组 × 256 个系数逐项通过；协议检查覆盖字节使能、busy 保护、非法访问、重复启动和复位中止 | [`results/accelerator_interface/rtl_sim/simulate.log`](../results/accelerator_interface/rtl_sim/simulate.log) |
| PYNQ-Z2 BIST 顶层 RTL | PASS，两次完整运行、256 个结果字检查和一次故障注入；时钟/按钮复位测试通过 | [`results/accelerator_interface/rtl_sim/board_simulate.log`](../results/accelerator_interface/rtl_sim/board_simulate.log) |
| Vivado 2024.2 独立实现 | PASS，WNS=0.732 ns、WHS=0.129 ns、BRAM=8、DSP=12 @ 100 MHz | [`results/accelerator_interface/vivado_impl/`](../results/accelerator_interface/vivado_impl/) |
| CPU+PQC 局部接口 | PASS，RV32IM-fast 执行 C 驱动，3 组、768 个系数 | [接口验证](MLKEM512_CPU_ACCEL_SMOKE.md) |
| CPU+PQC 官方 KAT | PASS，145/145 ML-KEM-512 | [`results/accelerator_cpu/kat/`](../results/accelerator_cpu/kat/)；端到端 0.9930×，当前为功能闭环而非性能收益 |
| PYNQ-Z2 实板烧录 | 待完成 | 已生成 [`mlkem512_basemul_k2_validation.bit`](../release/mlkem512_basemul_k2/mlkem512_basemul_k2_validation.bit)，尚未上板 |

## 官方数据口径

主机端的 435 条记录覆盖 ML-KEM-512/768/1024；PicoRV32已完成
ML-KEM-512三种CPU各145条，及ML-KEM-768/1024 RV32IM-fast各145条。CPU+PQC 加速版同样完成 145/145 条 ML-KEM-512 记录，
并核验了每条记录的 MMIO 调用计数、核心周期和输出。PicoRV32 的通过结果证明固定软件、
输入、输出和 RTL 执行路径一致，不代表正式 CAVP 认证，也不代表实体板结果。

## HLS 证据边界

新 HLS 只验证标准库 K=2 NTT 域 cached BaseMul。C 仿真、HLS 综合和独立 native
MMIO/BRAM RTL 已通过，但仍不验证 PicoRV32 总线接入、完整 NTT/INTT 或端到端 KEM。
HLS 报告的 137 cycles 与 adapter RTL 实测核心 136 cycles 都只属于核心边界，不能直接
换算系统加速比。

本轮修正了 C testbench 的 zeta 表漏项（`-1103, 430`），并重跑 103 个用例。历史
`hls_synthesis/summary.json` 保留当时综合和 C 仿真的源码哈希；计算核源码没有改动，
当前 C 验证使用修正后的 TB，证据为 `basemul_k2_csim.txt`。综合报告中的历史 TB 哈希
不应当作本轮 C 回归的哈希。
本轮源码、TB、XPR、日志、报告与 bitstream 的 SHA-256 见
[`delivery_manifest.json`](../results/accelerator_interface/delivery_manifest.json)。

## 可重复性要求

所有新测量都应保存：工具版本、参数集、CPU 配置、输入/输出哈希、核心周期、搬运周期、
CPU API 周期、资源、时序和实现日志。新结果写入 [`docs/BENCHMARKS.md`](BENCHMARKS.md)
和 [`docs/PROJECT_STATUS.md`](PROJECT_STATUS.md)，不要覆盖已有官方证据。
