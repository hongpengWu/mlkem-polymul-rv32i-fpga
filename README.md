# ML-KEM PolyMul · PicoRV32 · PYNQ-Z2

本仓库保存面向 PYNQ-Z2 的 ML-KEM/CRYSTALS-Kyber 研究工程。当前主线为
**ML-KEM-1024（K4）的 Keccak/SHAKE 软硬件协同加速**，以完整 API 收益和资源成本
指导架构。专用 HLS 入口见 [hls/mlkem1024_keccak](hls/mlkem1024_keccak/README.md)。
已有 CPU 官方基线和 K2 BaseMul 结果保留作为历史对照；最新路线见
[项目进度](docs/PROJECT_STATUS.md)。

当前状态（2026-10-05）：

- 新PS–PL交互式overlay已完成AXI协议/3条官方RTL用例与100 MHz物理签核，
  setup/hold为+0.302/+0.026 ns。部署包固定在`release/mlkem1024_pynq/`，
  含配套`.bit/.hwh`、Jupyter Notebook和145条官方向量；新overlay尚未上板验证。
  [部署与独立BD Tcl入口](docs/BUILD.md#k4-pspl--jupyter入口) ·
  [本次签核证据](results/keccak_cpu/pynq/20261005_psaxi06/result.json)

- K4 Keccak 两种访存配置均通过 109 次 C/RTL 协同测试；向量为本地 FIPS 202 差分测试。
  独立核的优化、资源和时序见 [测量记录](results/hls/mlkem1024_keccak/summary.md)。
- K4 历史RTL版本已通过**145/145官方记录**，同CPU/RAM测试集API总周期比**3.803×**。
  KeyGen/Encaps/Decaps分别4.203×/3.636×/3.602×；[原始日志与汇总](results/keccak_cpu/kat/summary.md)。
  该版本完整系统OOC为LUT19,084、FF16,970、BRAM34.5、DSP4；内部setup −1.367 ns。
- 当前`timing_decode_v3`优化RAM写控制与MMIO译码；10次硬件调用/216字、译码等价检查及最终官方145/145通过，API总周期比3.8028×。
  100 MHz布线后内部setup/hold为+0.269/+0.029 ns；LUT19,003、FF17,005、BRAM34.5、DSP4。
  原OOC resetn边界hold −1.194 ns失败证据保留；独立板级时序已通过。
  开发默认只跑索引0、1、115；当前145条已独立验收，3,188次真实HLS调用匹配。
  [当前全量证据](results/keccak_cpu/candidates/timing_decode_v3/kat/summary.md)。
  统一入口为[`run_flow.tcl`](scripts/mlkem1024_keccak/run_flow.tcl)顶部0/1开关，默认`FULL_KAT=0`。
- ML-KEM-768/1024 RV32IM-fast CPU-only RTL 官方回归各通过 145/145，使用 128 KiB RAM / 32 KiB 栈。
- K4 PYNQ-Z2 板级上板前签核已通过：真实 MMCM/复位三例子集 3/3、路由和 100 MHz 时序通过，
  packed LUT/FF/BRAM36 等效/DSP 为 19,030/16,963/34.5/4；用户报告烧录后LED0 PASS及BTN0重启通过。
  [板级证据](results/keccak_cpu/board/20261004_162430/result.json)

- ML-KEM-512 的 RV32I、RV32IM 迭代乘法、RV32IM 快速乘法三组 PicoRV32 RTL 回归各通过
  145 条固定版本官方记录。
- 主机端 ML-KEM-512/768/1024 共 435 条官方 ACVP/FIPS 203 记录通过。
- RV32IM-fast 的 512 全量阶段 profiling 已完成，数据在
  [`docs/MLKEM512_PROFILE.md`](docs/MLKEM512_PROFILE.md)。
- 新 HLS `mlkem512_basemul_acc_k2` C 仿真 103/103 通过，Vitis HLS 2024.2 综合通过，
  估算 II=1、137 cycles、150.83 MHz、DSP/LUT/FF/BRAM=12/310/599/0。
- 独立 MMIO/BRAM/板级 BIST RTL 仿真通过；Vivado 2024.2 PYNQ-Z2 工程实现通过，WNS/WHS
  为 0.732/0.129 ns，使用 8 个 BRAM 原语和 12 个 DSP，并已导出 bitstream。
- K2 RV32IM-fast＋BaseMul 已通过完整145条官方RTL回归；端到端为0.9930×。
  核心、搬运和完整API周期分别记录；K2结果不代表K4 Keccak系统性能。

## 目录

```text
rtl/cpu/                 PicoRV32 RTL
rtl/benchmark/           CPU-only 固件 RAM、时钟/复位和可配置 CPU wrapper
rtl/accelerator/         HLS 生成 RTL、BRAM、MMIO adapter 和 PYNQ-Z2 BIST 顶层
hls/mlkem512_basemul_k2/ K=2 NTT 域 cached BaseMul HLS、TB、Tcl、短路径脚本和 IP
hls/mlkem1024_keccak/   K4 Keccak/SHAKE HLS、TB、Tcl与证据脚本（生成工程在E:/hls）
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

K4标准软件与Keccak硬件的完整RTL闭环及历史全量周期对照已完成，当前板级上板前签核也已完成。
当前版本最终145条已通过；bitstream内置3例独立自检。实板烧录、PS/PL控制、全量数据装载和周期/结果读回及Jupyter演示待完成。完整计划见
[`docs/COMPETITION_ROADMAP.md`](docs/COMPETITION_ROADMAP.md)。

更多入口：

- [`docs/STRUCTURE.md`](docs/STRUCTURE.md)：目录职责和清理边界
- [`docs/VALIDATION.md`](docs/VALIDATION.md)：当前已完成验证
- [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)：性能、资源和证据索引
- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)：项目进度
- [`vectors/official_kat/acvp/SOURCES.md`](vectors/official_kat/acvp/SOURCES.md)：官方向量来源
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)：第三方许可和来源
