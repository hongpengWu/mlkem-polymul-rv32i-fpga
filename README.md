# ML-KEM PolyMul · PicoRV32 · PYNQ-Z2

本工程在 PYNQ-Z2 的 PL 端运行 PicoRV32，通过 AXI4-Lite 和 BRAM 接口驱动 ML-KEM 多项式乘法加速核。提供原始 RV32I 和 RV32IM 迭代乘法两种配置，默认仍为 RV32I。目标器件为 `xc7z020clg400-1`，板载 125 MHz 时钟经 MMCM 转为 100 MHz；工程采用纯 RTL，不使用 Zynq PS 或 Block Design。

运算为 `FNTT(A) → FNTT(B) → BaseMul → INTT → FinalScale`，计算环 `Z_3329[x]/(x^256+1)` 中的多项式乘法。这是完整 ML-KEM 算法中的运算模块。

当前以 **ML-KEM-512 为主要优化与展示对象**，768/1024 用于完整所选向量回归和扩展能力验证，
同时补充基本性能与存储开销。已经完成主机三参数集共 435 项官方回归，以及三种 PicoRV32
配置各 145 条 ML-KEM-512 官方记录的完整 API RTL 回归。RV32IM 快速乘法的
[全量阶段测量](docs/MLKEM512_PROFILE.md) 也已完成：主要 KEM 操作的 Keccak 占 71%–81%，
多项式算术占 13%–21%。下一步对齐标准库与加速核的接口，优先建立快速乘法 CPU 的
软件/硬件主线对照及 64 KiB 实现，再补其他 CPU 消融与 768/1024 回归，最后安排实板。
最新进度和任务清单见 [项目进度](docs/PROJECT_STATUS.md)。

![系统结构](docs/architecture.svg)

## 快速开始

使用 **Vivado 2024.2**，安装 Zynq-7000 器件支持。克隆后可直接打开 [mlkem_pynqz2.xpr](vivado/project/mlkem_pynqz2.xpr)。如需重新生成完整工程，从仓库根目录运行：

```text
vivado -mode batch -source scripts/run.tcl -tclargs project
```

生成的完整工程位于 `vivado/project/`，打开其中的 `mlkem_pynqz2.xpr` 即可使用 GUI。默认顶层为 `mlkem_polymul_pynqz2_top`，启用只读 VIO，固件为 `firmware/images/transfer_both_unroll4.mem`。

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio
vivado -mode batch -source scripts/run.tcl -tclargs implement
```

`vio` 运行板级仿真；`implement` 通过四组仿真后完成综合、布局布线和 bitstream 生成，导出烧录文件至 `release/`、报告至 `build/reports/`。工程创建和实现不会自动烧录开发板。

RV32IM 迭代乘法配置启用 PicoRV32 原有的乘除法单元（`MUL=1, FAST_MUL=0, DIV=1`），使用独立工程和输出目录：

```text
vivado -mode batch -source scripts/run.tcl -tclargs project firmware/images rv32im_iterative
vivado -mode batch -source scripts/run.tcl -tclargs cpu firmware/images rv32im_iterative
vivado -mode batch -source scripts/run.tcl -tclargs implement firmware/images rv32im_iterative
```

完整工程为 [RV32IM XPR](vivado/project_rv32im_iterative/mlkem_pynqz2.xpr)，烧录文件在 `release/rv32im_iterative/`。该配置通过 4096 项 M 指令检查、原四组回归及实现；测量表和原始证据入口见 [性能与资源数据](docs/BENCHMARKS.md)。当前 transfer 固件仍为不含 M 指令的原始 RV32I 镜像，因此系统回归用于验证兼容性；CPU-only 多项式 baseline 和 ML-KEM-512 完整 API 回归已完成。512 快速 CPU 阶段测量已完成；768/1024 CPU 回归、64 KiB 实现及软件/硬件端到端对照仍列入 [竞赛路线图](docs/COMPETITION_ROADMAP.md)，本轮未烧录实体板。

## 目录

```text
rtl/          CPU、加速核、AXI/BRAM 接口、系统与板级 RTL
constraints/  PYNQ-Z2 引脚、时钟与复位约束
hls/          HLS C++ 源码、独立 C 测试与配置
firmware/     transfer、多项式 baseline、ML-KEM KAT 的源码与独立镜像
tb/           CPU 指令、核心、板级、协议测试与周期监测器
firmware/cpu_baseline/  CPU-only 软件 NTT/BaseMul/INTT baseline
firmware/mlkem_baseline/ 历史官方 ML-KEM-512 KeyGen 首例入口
firmware/mlkem512_suite/ ML-KEM-512 六类操作的通用裸机驱动
rtl/benchmark/          CPU-only 可配置 RAM 系统（多项式 16 KiB；KAT 64 KiB）
scripts/cpu_baseline/   三种 ISA/乘法配置的构建、仿真与数据采集
scripts/mlkem_baseline/ 官方 KeyGen 的固件构建、三组仿真与结果汇总
scripts/mlkem512_suite/ 全部 145 条记录的构建、分批恢复与严格汇总
third_party/           固定提交、保持上游字节内容的 mlkem-native portable C
vivado/       Vivado 工程共享配置、完整工程与 VIO IP 配置
scripts/      工程创建、仿真、实现、固件编译与 JTAG 烧录入口
docs/         构建说明、目录职责、验证记录与性能数据表
results/      按配置保存的仿真日志、实现报告及校验记录
release/      按配置保存的 BIT 与匹配 LTX 烧录文件
build/        本地编译结果与报告（Git 忽略）
```

- [构建、仿真与烧录](docs/BUILD.md)
- [目录与维护规则](docs/STRUCTURE.md)
- [验证记录](docs/VALIDATION.md)
- [性能与资源数据表](docs/BENCHMARKS.md)
- [ML-KEM-512 CPU baseline 分析](docs/MLKEM512_BASELINE_ANALYSIS.md)
- [竞赛路线图与阶段门](docs/COMPETITION_ROADMAP.md)
- [CPU baseline 协议](docs/CPU_BENCHMARK_PROTOCOL.md)
- [ML-KEM-512 完整回归协议](docs/MLKEM512_BENCHMARK_PROTOCOL.md)
- [ML-KEM-512 加速器接口契约](docs/MLKEM512_ACCELERATOR_INTERFACE.md)
- [官方 FIPS 203/ACVP 向量来源](vectors/official_kat/acvp/SOURCES.md)
- [保留源码哈希清单](docs/source_integrity.csv)
- [后续配置变更清单](docs/source_changes.csv)
- [第三方组件说明](THIRD_PARTY_NOTICES.md)

主机端 FIPS 203/ACVP 参考验证使用固定的 `mlkem-native` 源码快照和仓库内的官方 JSON
向量。先做结构与哈希检查，再运行三组 ML-KEM-512/768/1024 的 keyGen、encapsulation、
decapsulation 和 key-check 用例：

```powershell
python scripts/kat/validate_acvp_json.py
./scripts/kat/run_host_acvp.ps1
```

主机参考实现共通过 435 条记录，覆盖 512/768/1024，记录位于 `results/official_reference/`。
PicoRV32 的 RV32I、RV32IM 迭代、RV32IM 快速三配置已各通过 **ML-KEM-512 全部 145 条
固定版本官方记录**，包括 KeyGen、Encaps、展开密钥 Decaps、种子形式 Decaps 和两类密钥检查。
每配置核对 148,160 B 输入及 101,760 B 输出，30 条 Decaps 中有 15 条预期隐式拒绝密钥；
实际 rdcycle、八类 M 指令、栈边界与输入哈希均经过检查。CPU 的 435 次执行是同一个 512
集合在三种配置上的重复覆盖，与主机三参数集共 435 条的口径不同。

全部操作分布见 [512 汇总](results/official_baseline/mlkem512/summary.md)，可复核现有结果：

```text
python scripts/mlkem512_suite/collect_resumed.py --check
```

结果由保留的 94 条关机前记录与 44 个独立完成批次合并，各原始身份恰好一次；
未拼造单次全套 PASS，无法恢复的整套启动周期和全程 M 总数保持为空。
三组使用 64 KiB RAM、16 KiB 栈预留，最大观测算法栈为 12,928 B；
RV32I/RV32IM 有效镜像为 27,808 / 26,272 B。观测栈不是最坏输入上界，
100 MHz 时间仅为仿真周期换算。可打开的主套件工程为 `vivado/mlkem512_<config>/mlkem512.xpr`；
重建、恢复和证据归档命令见 [构建说明](docs/BUILD.md#picorv32-ml-kem-512-完整公开向量集)。
当前尚无该 64 KiB 配置的实现报告或 bitstream；768/1024 CPU、加速器集成和实板验证待完成。

**历史 KeyGen 首例**仍单独保留，用以下入口复现：

```text
python scripts/mlkem_baseline/build.py
vivado -mode batch -source scripts/mlkem_baseline/run.tcl -tclargs rv32i
vivado -mode batch -source scripts/mlkem_baseline/run.tcl -tclargs rv32im_iterative
vivado -mode batch -source scripts/mlkem_baseline/run.tcl -tclargs rv32im_fast
python scripts/mlkem_baseline/collect.py
```

历史首例三组使用相同的 portable C 算法、官方输入、64 KiB RAM 和 16 KiB 栈。KeyGen 原始
周期分别为 8,995,082、5,812,531、5,194,547；按 100 MHz 仿真时钟换算为
89.95082、58.12531、51.94547 ms。详见
[KeyGen 汇总表](results/official_baseline/keygen512_tc1/summary.md) 和
[构建说明](docs/BUILD.md#picorv32-官方-ml-kem-512-keygen)。
`vivado/mlkem_keygen_*/*.xpr` 是历史首例仿真工程。该单例驱动与当前通用驱动的外围指令
不同，保留原测量口径，不将单例值当作完整记录分布。

CPU-only 软件 baseline 的三组仿真、Vivado 2024.2 实现和 bitstream 由以下入口复现；它们不连接 PQC 加速器：

```text
python scripts/cpu_baseline/build.py
vivado -mode batch -source scripts/cpu_baseline/run.tcl -tclargs rv32i
vivado -mode batch -source scripts/cpu_baseline/run.tcl -tclargs rv32im_iterative
vivado -mode batch -source scripts/cpu_baseline/run.tcl -tclargs rv32im_fast
vivado -mode batch -source scripts/cpu_baseline/implement.tcl -tclargs rv32i
```

对另外两组执行 `implement.tcl` 时只替换最后一个配置名。`results/cpu_baseline/` 保存可审计的日志、资源/时序报告和构建哈希；`vivado/cpu_baseline_*/*.xpr` 是可直接打开的 CPU-only 工程。

版本库包含 `.xpr`、VIO `.xci` 和 `release/` 烧录文件。仿真、综合、实现缓存保留在本地，并由 Git 忽略。

初始目录整理保留了 52 个功能源码、测试及初始化文件的原始内容。阶段 2 仅对其中 4 个系统/板级封装与 TB 文件增加 CPU 参数透传，另 48 个文件保持原始哈希；变更记录于 `docs/source_changes.csv`，可运行 `./scripts/verify_sources.ps1` 核对。PicoRV32 内核、加速器、原有 transfer 固件和约束未改动。新增 KeyGen 首例、512 全量入口与旧 baseline 分目录维护，所引入的 mlkem-native portable 源码保持上游 Git blob 字节内容，构建时核验 `third_party/mlkem-native/SOURCE_MANIFEST.json`。`rtl/accelerator/` 是原有 Vitis HLS 2025.2 生成的 RTL，本工程使用 Vivado 2024.2 构建该快照，并未用 HLS 2024.2 重新生成或证明两版 HLS 输出等价。
