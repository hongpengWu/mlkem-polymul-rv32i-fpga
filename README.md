# ML-KEM PolyMul · PicoRV32 · PYNQ-Z2

本仓库保存面向 PYNQ-Z2 的 ML-KEM/CRYSTALS-Kyber 研究工程。当前主线为
**ML-KEM-1024（K4）的 Keccak/SHAKE 软硬件协同加速**，以完整 API 收益和资源成本
指导架构。专用 HLS 入口见 [mainline/k4/hls](mainline/k4/hls/README.md)。
已有 CPU 官方基线和 K2 BaseMul 结果保留作为历史对照；最新路线见
[项目进度](docs/PROJECT_STATUS.md)。

当前状态（2026-10-26）：

- 新PS–PL交互式overlay已完成AXI协议、100 MHz物理签核，并在 PYNQ-Z2 上完成官方 `145/145 FULL_PASS`，
  setup/hold为+0.302/+0.026 ns。配套部署包已纳入`release/mlkem1024_pynq/`，
  含配套`.bit/.hwh`、Jupyter Notebook和145条官方向量；板上 API 总计446,852,439 cycles，批量墙钟约9.563 s。
  [部署与独立BD Tcl入口](docs/BUILD.md#k4-pspl--jupyter入口) ·
  [本次签核证据](results/keccak_cpu/pynq/20261005_psaxi06/result.json) ·
  [145条实板证据与复核](results/keccak_cpu/board/20261016_full145/README.md)

- **同板对照已完成：实板API加速3.8028×，PS整批加速2.2976×。** 两组各145条官方记录全部通过，
  API周期1,699,293,290 → 446,852,439；包含PS传输/校验的整批墙钟22.135 → 9.634秒。
  同RV32IM-fast、100 MHz、128 KiB RAM / 32 KiB栈、同bitstream切换软件/硬件FIPS202服务。
  代表例两组共60次重复、6项恢复检查均通过；
  [实板原始证据与复核](results/k4/paired_firmware/board_20261023/summary.md) · [分层计时](docs/BENCHMARKS.md)。

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
  统一入口为[`flow.tcl`](mainline/k4/flow.tcl)顶部0/1开关，默认`FULL_KAT=0`。
- ML-KEM-768/1024 RV32IM-fast CPU-only RTL 官方回归各通过 145/145，使用 128 KiB RAM / 32 KiB 栈。
- 此前独立 PL 自检已通过：真实 MMCM/复位三例、路由和 100 MHz 时序通过，
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

## 目录与复现

当前发布分支为 **`last`**，K4源码统一在 **[mainline/k4/](mainline/k4/README.md)**。

竞赛工程报告见 [docs/COMPETITION_REPORT.md](docs/COMPETITION_REPORT.md)，其中区分
RTL/仿真、PS-PL 实现和 PYNQ-Z2 实板数据。
报告 DOCX、配套模板和图片生成脚本集中在[`docs/competition/`](docs/competition/README.md)，
按其中步骤可从仓库根目录重建。

```text
mainline/k4/   当前HLS、RTL、固件、TB、约束、Notebook和两个Tcl入口
results/       统一历史与新增验证证据
release/       配套部署包和少量发布bitstream
build/         本地生成工程和中间文件，不提交Git
```

主流程使用 `mainline/k4/flow.tcl`，PS–PL流程使用 `mainline/k4/bd_axi.tcl`。
工具由PATH/环境变量定位，仓库依赖以脚本位置解析；短构建目录可配置。
共用CPU、标准库、官方向量及历史基线保留原位。
详见 [目录说明](docs/STRUCTURE.md)、[构建说明](docs/BUILD.md) 和
[迁移验证记录](results/reorganization/)。

`release/mlkem1024_pynq/` 是可选的预构建部署包：`.bit`、`.hwh`、驱动、Notebook、
145条向量和 manifest 必须保留在同一目录。manifest 中记录的旧构建目录只用于追溯，
运行时不访问该路径；从源码复现时使用上面的仓库相对路径。包内 README 是生成时的记录，
板上全量及配对实测以本仓库相应原始证据为准。

## 从干净克隆开始

下面的预检不启动 Vivado、Vitis HLS、XSim 或 KAT。要求 Python 3.10 或更新版本；若安装了 `tclsh`，
会顺带检查两个 Tcl 入口的语法及 `CHECK_ONLY` 路径。命令均从仓库根目录运行：

```powershell
git clone https://github.com/hongpengWu/mlkem-polymul-rv32i-fpga.git
Set-Location mlkem-polymul-rv32i-fpga
git checkout last
python scripts/check_repository.py --paired-dir release/mlkem1024_pynq
tclsh mainline/k4/flow.tcl
tclsh mainline/k4/bd_axi.tcl
```

预检核对 Python/Notebook 语法、官方向量及SHA-256、生成的K4 fixture、第三方源码清单、
发布包文件哈希和 Tcl 输入路径。通过表示文件与轻量路径检查通过；它不替代 C/RTL 仿真、
综合、布局布线或实板测试。工具版本、所需环境变量、阶段开关和运行命令见
[`docs/BUILD.md`](docs/BUILD.md) 与 [`mainline/k4/README.md`](mainline/k4/README.md)。

`release_manifest.json` 和冻结历史证据可能保留采集时的绝对路径，作为来源记录；
复现脚本不读取这些路径，发布包只按本地文件名和哈希装载。新运行目录从 Tcl 入口相对仓库根解析，
工具安装位置通过 `PATH` 或环境变量提供。

## 软件 baseline

使用 Vivado 2024.2 通过脚本生成并运行三组 CPU-only 工程。生成的 Vivado 项目保存在
被忽略的 `vivado/` 本地构建目录；源码仓库不保留含开发机绝对路径的 `.xpr` 快照：

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

## 历史 K2 HLS 对照

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

K4标准软件与Keccak硬件的完整RTL闭环、板级签核和 PYNQ-Z2 全量实板验证已完成。
独立 PL 自检 bitstream 内置3例；本次 PS–PL overlay 由 Jupyter 动态装载145条输入，
完成结果核对、周期读回和证据导出。完整计划见
[`docs/COMPETITION_ROADMAP.md`](docs/COMPETITION_ROADMAP.md)。

同条件CPU-only实板对照、代表例重复和限定恢复专项已完成；接下来完善报告和演示。
功耗、长期稳定性、K3扩展和其他CPU消融后置。
官方公开向量通过不等同于 CAVP/FIPS 认证。

更多入口：

- [`docs/STRUCTURE.md`](docs/STRUCTURE.md)：目录职责和清理边界
- [`docs/VALIDATION.md`](docs/VALIDATION.md)：当前已完成验证
- [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)：性能、资源和证据索引
- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)：项目进度
- [`vectors/official_kat/acvp/SOURCES.md`](vectors/official_kat/acvp/SOURCES.md)：官方向量来源
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)：第三方许可和来源
