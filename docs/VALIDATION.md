# 验证记录

更新时间：2026-09-25。本文只记录当前仍在仓库中的验证入口和证据；旧完整加速器的
板级仿真、实现报告和 bitstream 已随旧主线删除。

## 当前结果

| 项目 | 状态 | 证据 |
|---|---|---|
| CPU-only 多项式 baseline | PASS，RV32I/RV32IM-iterative/RV32IM-fast 各 8 组、4096 项检查 | [`results/cpu_baseline/`](../results/cpu_baseline/) |
| ML-KEM-512 官方 PicoRV32 回归 | PASS，三种 CPU 各 145/145 | [`results/official_baseline/mlkem512/`](../results/official_baseline/mlkem512/) |
| 主机端 FIPS 203/ACVP | PASS，512/768/1024 合计 435 条 | [`results/official_reference/`](../results/official_reference/) |
| KeyGen 官方 tcId=1 | PASS，三种 CPU | [`results/official_baseline/keygen512_tc1/`](../results/official_baseline/keygen512_tc1/) |
| RV32IM 指令配置 | PASS，迭代和快速乘法配置均在软件回归中使用 | [`tb/cpu/`](../tb/cpu/) |
| 新 HLS C 仿真 | PASS，103/103 | [`results/accelerator_interface/basemul_k2_csim.txt`](../results/accelerator_interface/basemul_k2_csim.txt) |
| 新 HLS 2024.2 综合 | PASS，II=1，估算 137 cycles、150.83 MHz | [`results/accelerator_interface/hls_synthesis/`](../results/accelerator_interface/hls_synthesis/) |
| 新 HLS Vivado 顶层 | 待完成 | 需要新 AXI/BRAM adapter 和 CPU 顶层 |
| CPU+PQC 官方 KAT | 待完成 | 新硬件接口尚未接入 |
| PYNQ-Z2 实板烧录 | 待完成 | 新顶层 bitstream 尚未生成 |

## 官方数据口径

主机端的 435 条记录覆盖 ML-KEM-512/768/1024；PicoRV32 当前完整 RTL 套件只覆盖
ML-KEM-512，每种 CPU 145 条。PicoRV32 的通过结果证明固定软件、输入、输出和 RTL
执行路径一致，不代表正式 CAVP 认证，也不代表实体板结果。

## HLS 证据边界

新 HLS 只验证标准库 K=2 NTT 域 cached BaseMul。C 仿真和 HLS 综合不验证 AXI 时序、
CPU 地址映射、完整 NTT/INTT 或端到端 KEM；这些必须在后续独立 Vivado 工程中验证。
137 cycles 是 HLS 核心估算，不能直接换算系统加速比。

## 可重复性要求

所有新测量都应保存：工具版本、参数集、CPU 配置、输入/输出哈希、核心周期、搬运周期、
CPU API 周期、资源、时序和实现日志。新结果写入 [`docs/BENCHMARKS.md`](BENCHMARKS.md)
和 [`docs/PROJECT_STATUS.md`](PROJECT_STATUS.md)，不要覆盖已有官方证据。
