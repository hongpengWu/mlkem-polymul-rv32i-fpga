# ML-KEM PolyMul · PicoRV32 · PYNQ-Z2

本仓库保存一个面向 PYNQ-Z2 的 ML-KEM/CRYSTALS-Kyber 研究工程。当前可复现主线是
PicoRV32 CPU 软件 baseline、FIPS 203/ACVP 官方向量回归，以及从标准库接口重新设计并
完成独立 MMIO/BRAM/板级 BIST 验证的 ML-KEM-512 K=2 BaseMul HLS 原型。旧的完整时域
多项式加速器和与之绑定的板级工程已移除，避免把失效的 AXI 地址映射、旧 bitstream 和
新接口混在一起。

当前主线状态：

- ML-KEM-512 的 RV32I、RV32IM 迭代乘法、RV32IM 快速乘法三组 PicoRV32 RTL 回归各通过
  145 条固定版本官方记录。
- 主机端 ML-KEM-512/768/1024 共 435 条官方 ACVP/FIPS 203 记录通过。
- RV32IM-fast 的 512 全量阶段 profiling 已完成，数据在
  [`docs/MLKEM512_PROFILE.md`](docs/MLKEM512_PROFILE.md)。
- 新 HLS `mlkem512_basemul_acc_k2` C 仿真 103/103 通过，Vitis HLS 2024.2 综合通过，
  估算 II=1、137 cycles、150.83 MHz、DSP/LUT/FF/BRAM=12/310/599/0。
- 独立 MMIO/BRAM/板级 BIST RTL 仿真通过；Vivado 2024.2 PYNQ-Z2 工程实现通过，WNS/WHS
  为 0.732/0.129 ns，使用 8 个 BRAM 原语和 12 个 DSP，并已导出 bitstream。
- RV32IM-fast＋MMIO 驱动最小闭环通过 3 组、768 个系数；完整 KEM 尚未接入，因此核心周期、搬运周期和完整 KEM 周期仍需分别
  记录，不能把 137 cycles 当作端到端加速比。

## 目录

```text
rtl/cpu/                 PicoRV32 RTL
rtl/benchmark/           CPU-only 固件 RAM、时钟/复位和可配置 CPU wrapper
rtl/accelerator/         HLS 生成 RTL、BRAM、MMIO adapter 和 PYNQ-Z2 BIST 顶层
hls/mlkem512_basemul_k2/ K=2 NTT 域 cached BaseMul HLS、TB、Tcl、短路径脚本和 IP
firmware/cpu_baseline/   CPU-only 多项式 baseline
firmware/mlkem_baseline/ 官方 KeyGen 入口
firmware/mlkem512_suite/ ML-KEM-512 完整官方套件入口
firmware/mlkem512_profile/ 阶段 profiling 入口
firmware/images/         可复现的 CPU/ML-KEM 固件镜像
tb/cpu/                  RV32IM 指令验证
tb/software/             多项式、KeyGen、完整 ML-KEM-512 软件 testbench
tb/accelerator/          MMIO、BRAM、板级 BIST 仿真与确定性向量
scripts/cpu_baseline/    三种 CPU 配置的构建、仿真、实现和汇总
scripts/mlkem_baseline/  KeyGen 构建与仿真
scripts/mlkem512_suite/  145 条官方记录的分批运行与恢复
scripts/mlkem512_profile/阶段 profiling
scripts/mlkem512_interface/接口审计和 BaseMul oracle
scripts/kat/             ACVP JSON 检查和主机端参考回归
scripts/mlkem512_basemul_k2/ 独立加速器 Vivado 仿真、实现、报告和 bitstream 脚本
vivado/                  可直接打开的 CPU-only/ML-KEM 软件和独立加速器 XPR
release/                 CPU-only baseline 与独立加速器 bitstream
results/                 官方回归、CPU 资源、HLS 综合和加速器实现证据
vectors/official_kat/    固定版本 FIPS 203/ACVP 输入与预期结果
third_party/             固定提交的 mlkem-native portable C 子集
docs/                    构建、验证、性能和路线记录
constraints/             PYNQ-Z2 时钟、引脚及复位约束
```

## 软件 baseline

使用 Vivado 2024.2 可打开 `vivado/cpu_baseline_<config>/cpu_baseline.xpr`，或重新构建
三组 CPU-only 工程：

```powershell
python scripts/cpu_baseline/build.py
vivado -mode batch -source scripts/cpu_baseline/run.tcl -tclargs rv32i
vivado -mode batch -source scripts/cpu_baseline/run.tcl -tclargs rv32im_iterative
vivado -mode batch -source scripts/cpu_baseline/run.tcl -tclargs rv32im_fast
```

实现资源和时序报告由 `scripts/cpu_baseline/implement.tcl` 生成，结果保存在
`results/cpu_baseline/`。ML-KEM-512 官方全集使用：

```powershell
python scripts/kat/validate_acvp_json.py
powershell -ExecutionPolicy Bypass -File scripts/kat/run_host_acvp.ps1
python scripts/mlkem512_suite/collect_resumed.py --check
```

三组 PicoRV32 的完整运行入口和恢复方法见 [`docs/BUILD.md`](docs/BUILD.md)；结果汇总见
[`results/official_baseline/mlkem512/summary.md`](results/official_baseline/mlkem512/summary.md)。
这是真实 RTL 仿真证据，不等同于 CAVP 认证或实体板验收。

## 新 HLS

新核只实现标准库 `polyvec_basemul_acc_montgomery_cached()` 的 ML-KEM-512 `K=2` NTT 域
向量点积：输入 `a[2][256]`、`b[2][256]`、`b_cache[2][128]`，输出 `result[256]`。
它不执行 NTT、逆 NTT、压缩或 1441 缩放。接口契约见
[`docs/MLKEM512_ACCELERATOR_INTERFACE.md`](docs/MLKEM512_ACCELERATOR_INTERFACE.md)。

```powershell
powershell -ExecutionPolicy Bypass -File hls/mlkem512_basemul_k2/run_csim.ps1
powershell -ExecutionPolicy Bypass -File hls/mlkem512_basemul_k2/run_hls_short.ps1
```

`run_hls_short.ps1` 会把工程暂存到短路径后调用 Vitis HLS 2024.2，适用于 Windows 长路径
限制。源文件、TB、配置、Tcl 和导出的 IP 保存在 `hls/mlkem512_basemul_k2/`。

## 研究边界

当前仓库不再声称存在可烧录的“旧完整加速器系统”。新 HLS 已通过独立 MMIO/BRAM adapter、
PYNQ-Z2 BIST 顶层和 Vivado 2024.2 实现验证；RV32IM-fast 驱动最小闭环也已通过，下一阶段接入标准 ML-KEM 软件，
再用同一官方向量和统一计时边界比较 CPU-only 与 CPU+PQC 硬件。完整计划见
[`docs/COMPETITION_ROADMAP.md`](docs/COMPETITION_ROADMAP.md)。

更多入口：

- [`docs/STRUCTURE.md`](docs/STRUCTURE.md)：目录职责和清理边界
- [`docs/VALIDATION.md`](docs/VALIDATION.md)：当前已完成验证
- [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)：性能、资源和证据索引
- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)：项目进度
- [`vectors/official_kat/acvp/SOURCES.md`](vectors/official_kat/acvp/SOURCES.md)：官方向量来源
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)：第三方许可和来源
