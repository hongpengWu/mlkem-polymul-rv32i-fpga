# 构建、仿真与烧录

ML-KEM-512 的 RV32IM 快速乘法阶段分析使用独立镜像和仿真入口。首次构建、
首批验证、全量续跑与暂停命令见 [分阶段测量说明](MLKEM512_PROFILE.md#重现与断点续跑)；
原始未插桩的软件 baseline 仍使用下文的 `mlkem512_suite` 入口。

## 环境

- Vivado 2024.2，包含 Zynq-7000 器件支持；构建脚本会检查版本。
- HLS C 仿真或重新综合时使用 Vitis HLS 2024.2。
- 重新编译固件时需要 PowerShell 和 `riscv64-unknown-elf-gcc` 工具链；使用预编译镜像时不需要 GCC。

除 HLS 命令外，下列命令均从仓库根目录执行。脚本根据自身位置定位源码，不依赖固定安装路径。当前机器的 PowerShell 示例：

```powershell
& 'E:\Xilinx\Vivado\2024.2\bin\vivado.bat' -mode batch -source scripts/run.tcl -tclargs project
```

如果已经设置 Vivado 环境，直接使用下文的 `vivado` 命令。

## 主机端 FIPS 203/ACVP 参考验证

仓库保存 ACVP-Server 固定提交导出的正式 FIPS 203 向量，并将 `FIPS203-tr1` 过渡向量单独
保存。来源、提交、文件哈希和采集日期见
[vectors/official_kat/acvp/SOURCES.md](../vectors/official_kat/acvp/SOURCES.md)。校验向量结构：

```powershell
python scripts/kat/validate_acvp_json.py
```

主机参考实现使用忽略目录 `build/kat_sources/mlkem-native/` 中固定提交的 `mlkem-native`。
Windows 下需要 Git for Windows 的 Bash、GCC、Make 和 Python；脚本会自动选择常见的 Bash
路径，也可以显式指定：

```powershell
./scripts/kat/run_host_acvp.ps1 -BashPath 'D:\Git\bin\bash.exe'
```

脚本在需要时用 `make SHELL=<git-bash>/sh.exe CC=gcc OPT=0 Q= acvp` 构建三个参数集，随后
运行正式 FIPS 203 和过渡 `FIPS203-tr1` 的全部向量。日志与元数据保存到
`results/official_reference/`。当前通过结果为 75 + 165 + 195 = 435 个用例；这只是主机
参考实现证据，不能代替 PicoRV32 固件仿真、CPU+加速器集成或实体板验证。

## PicoRV32 官方 ML-KEM-512 KeyGen

本阶段在 PicoRV32 RTL 上运行正式 FIPS 203/ACVP `keyGen` 的首个 ML-KEM-512
用例（`vsId=42, tgId=1, tcId=1`）。程序使用固定提交的 mlkem-native portable C
实现，输入为官方 32 字节 `d` 和 32 字节 `z`，调用确定性 `KeyGen_Internal` 接口。
这一个历史里程碑的通过范围独立于主机端 435 个用例；后续 ML-KEM-512 全集回归
使用下方的独立入口和结果目录，其他参数集仍需另行验证。

从仓库根目录构建两份裸机固件并运行三组仿真：

```text
python scripts/mlkem_baseline/build.py
vivado -mode batch -source scripts/mlkem_baseline/run.tcl -tclargs rv32i
vivado -mode batch -source scripts/mlkem_baseline/run.tcl -tclargs rv32im_iterative
vivado -mode batch -source scripts/mlkem_baseline/run.tcl -tclargs rv32im_fast
python scripts/mlkem_baseline/collect.py
```

`build.py` 默认使用本机 Vivado 2024.2 附带的 GCC 13.3.0；换机器时用
`--tool-dir YOUR_RISCV_BIN_DIRECTORY` 指定工具目录。脚本先检查上游源码与官方
JSON 哈希，再从 JSON 生成 `tb/software/mlkem_keygen/` 中的输入头、输入 `.mem`、
期望输出 `.mem` 和来源清单。编译目标为 `rv32i/ilp32` 与 `rv32im/ilp32`，其余选项
一致，优化级别为 `-O3`；迭代和快速乘法 CPU 使用同一份 RV32IM 镜像。源码按多个
独立 `.c` 编译单元构建，未使用原生指令集优化后端；配置和裸机运行库位于
`firmware/mlkem_baseline/`，上游算法文件保持原样。

| 配置 | Vivado 2024.2 仿真工程 | 固件 |
|---|---|---|
| RV32I | `vivado/mlkem_keygen_rv32i/mlkem_keygen.xpr` | `firmware/images/mlkem_keygen/rv32i.mem` |
| RV32IM 迭代 | `vivado/mlkem_keygen_rv32im_iterative/mlkem_keygen.xpr` | `firmware/images/mlkem_keygen/rv32im.mem` |
| RV32IM 快速 | `vivado/mlkem_keygen_rv32im_fast/mlkem_keygen.xpr` | 同一 RV32IM 镜像 |

三组都使用现有 `cpu_benchmark_system` 的真实 PicoRV32、AXI 响应路径和 XPM 同步
RAM，统一设置 `RAM_ADDR_BITS=14`（64 KiB）。链接脚本保留 16 KiB 栈，范围为
`0xbff0..0xfff0`，并拒绝静态镜像与栈重叠。三组运行观察到的最低栈指针均为
`0xdb80`，本用例使用 9,328 字节；这不是全部 ML-KEM 输入的最大栈使用证明。

testbench 逐字节检查传给 KeyGen 的 64 字节输入及完整 `ek`（800 字节）和
`dk`（1,632 字节）。期望输出只由 testbench 读取，不进入固件镜像。它还检查执行
顺序、真实 `rdcycle` 差值、M 指令完成情况、栈边界、地址越界和 CPU trap。
成功必须出现 `MLKEM_KEYGEN_PASS cases=1 input_bytes=64 output_bytes=2432`。

测量区间仅包含完整 KeyGen 调用；输入准备和 MMIO 导出在区间之外。原始周期为
RV32I 8,995,082、迭代 RV32IM 5,812,531、快速 RV32IM 5,194,547。按 100 MHz
仿真时钟可换算时间；本阶段未测量布局布线后的最高频率。三组日志与构建哈希位于
`results/official_baseline/keygen512_tc1/`，`collect.py` 生成同目录的
`summary.json`、`summary.csv` 和 [summary.md](../results/official_baseline/keygen512_tc1/summary.md)。

重现“错误预期输出必须被拒绝”的检查：

```text
vivado -mode batch -source scripts/mlkem_baseline/verify_rejection.tcl
python scripts/mlkem_baseline/collect.py --check
```

该检查只改 `build/` 下的 expected 副本，翻转公钥首字节一个 bit。仿真应出现指定的
`MLKEM_KEYGEN_FAIL byte mismatch`，外层脚本确认原因正确后输出
`MLKEM_REJECTION_CHECK_PASS`；这份预期失败日志独立保存在 `negative_check/`。
`collect.py --check` 校验当前镜像、官方 fixture、构建清单和三组结果，不重写汇总。

上述 `.xpr` 可直接打开用于仿真。本阶段没有创建新的板级实现、资源/时序报告或
烧录 bitstream；旧 16 KiB 多项式 baseline 的资源数字不能作为新 64 KiB 系统的
实现结果。已有 RTL、HLS 和旧固件保持原状。后续依次扩展 Encaps/Decaps、完整
官方用例，再进行相同 RAM 配置的实现和实体板验证。

## PicoRV32 ML-KEM-512 完整公开向量集

完整 512 回归包含 145 项 KeyGen、Encaps、Decaps、种子形式 Decaps 和密钥检查。
三种 CPU 使用同一通用驱动，旧首例工程保留不变。

```text
python scripts/mlkem512_suite/build.py
python scripts/mlkem512_suite/run.py
python scripts/mlkem512_suite/collect.py
```

`run.py` 并行运行三配置，也可用 `--config rv32i|rv32im_iterative|rv32im_fast` 单独运行。
默认工具路径沿用本机 2024.2，可通过 `build.py --tool-dir` 和 `run.py --vivado` 指定。
工程为 `vivado/mlkem512_<config>/mlkem512.xpr`，结果目录为
`results/official_baseline/mlkem512/`。原始输入由仿真邮箱逐例装入，预期值仅供 TB 使用；
计时边界、操作区别及覆盖范围见 [512 测量协议](MLKEM512_BENCHMARK_PROTOCOL.md)。
这是 CPU RTL 回归入口，未接入 PQC 加速器或板级输入通道。

### 从关机断点继续

2026-09-24 关机前保存了 RV32I 25 条、迭代 RV32IM 31 条、快速 RV32IM 38 条，
共 94 条已完成记录；对应 CSV、原始控制台、输入哈希和文件快照保留于
`results/official_baseline/mlkem512/checkpoint/`。这些是通过逐例检查的记录，
三组原日志均没有完整 145 条的最终 PASS，不能据此认定全套已通过。

恢复使用原固件、CPU RTL 和官方 fixture，不要重新构建固件或从头运行 `run.py`。
在仓库根目录执行：

```text
python scripts/mlkem512_suite/collect_resumed.py --check-checkpoint
python scripts/mlkem512_suite/resume.py --prepare-only
python scripts/mlkem512_suite/resume.py --workers 4
python scripts/mlkem512_suite/collect_resumed.py --archive-project-evidence
python scripts/mlkem512_suite/collect_resumed.py
```

`resume.py` 默认每批最多 8 条，剩余 120／114／107 条形成 15／15／14 个批次，
共 44 批。已有分批方案会复用，不会因后续改变 `--batch-size` 而重新分组。
每批保留本地索引与原始 `case_index` 的映射，固件和计时方法不变；
TB 用 `EXPECTED_CASES` 检查该批长度。默认使用 4 个并发工作进程；本次确认内存余量后
以 `--workers 6` 完成，不应同时运行第二个恢复进程。
工具位置可由 `resume.py --vivado` 指定。

每批结果位于 `results/official_baseline/mlkem512/batches/<config>/batch_<首索引>_<末索引>/`，
独立工程位于 `build/mlkem512_suite/batches/<config>/<batch>/mlkem512.xpr`。
启动前冻结输入哈希，退出后复核；仅在真实批次 PASS、逐例及来源验证通过后保留
`success.json`。再次运行会重新验证并跳过成功批次。若强制终止正在计算的批次，
该批未完成前缀不会自动保存，下次需重跑该批；既有 checkpoint 和成功批次不受影响。

`--archive-project-evidence` 会先完整校验已成功批次，再把原 `.xpr` 复制为结果目录中的
`project.xpr`，并将实际暂存镜像、fixture 和日志的哈希保存到 `project_evidence.json`。
该命令可重复执行；删除忽略的 `build/` 缓存前应完成归档，最终汇总也要求这些归档证据。
本地缓存存在时仍检查实际暂存文件；缓存缺失时核对归档哈希和同样的 CPU／批长参数。
归档 `.xpr` 用于来源核验；在 Vivado 打开主套件时仍使用 `vivado/mlkem512_<config>/mlkem512.xpr`。

需要正常暂停时创建 STOP 文件，调度器停止派发新批次并等待已经启动的批次结束：

```powershell
New-Item -ItemType File -Path build/mlkem512_suite/STOP -Force
```

恢复前删除该文件，再执行 `resume.py`：

```powershell
Remove-Item -LiteralPath build/mlkem512_suite/STOP
python scripts/mlkem512_suite/resume.py --workers 4
```

`collect_resumed.py` 只有在三组各 145 个原始身份唯一且齐全、字节总数和 M 指令计数
交叉校验通过后才生成 `summary.json`、`cases.csv`、`summary.md`；`--check` 只验证。
汇总明确区分已保存前缀与独立完成的批次，不拼造单次 145 条 PASS。
旧前缀缺少结束记录，因此全程周期和 M 总数记为未知；续跑批次总数另列，
全部 145 条的算法区间周期、M 计数和观测栈深仍可按原始身份统计。

## 创建完整工程

```text
vivado -mode batch -source scripts/run.tcl -tclargs project
```

省略 `-tclargs project` 时同样创建工程。共享配置位于 `vivado/project.tcl`；生成工程位于：

```text
vivado/project/mlkem_pynqz2.xpr
```

该工程包含 RTL、初始化文件、约束、VIO IP 和四个仿真集。可通过 Vivado 的 **Open Project** 打开 `.xpr`，并在 Simulation Sources 中选择仿真集：

| 仿真集 | 顶层 | 用途 |
|---|---|---|
| `sim_1` | `tb_pynqz2_profile_vio` | 默认板级与 VIO 验证 |
| `sim_board` | `tb_pynqz2_bram_board` | 无 VIO 的 LED 与按钮复位验证 |
| `sim_protocol` | `tb_bram_wrapper_protocol` | AXI/BRAM 协议与边界用例 |
| `sim_core` | `tb_v39e_true_one_dsp` | 加速核独立算术验证 |

通过第三个位置参数选择 RV32IM 迭代乘法配置：

```text
vivado -mode batch -source scripts/run.tcl -tclargs project firmware/images rv32im_iterative
```

完整参数顺序为 `模式 固件目录 CPU配置`，配置可选 `rv32i`（默认）或 `rv32im_iterative`。迭代配置将 `CPU_ENABLE_MUL=1`、`CPU_ENABLE_FAST_MUL=0`、`CPU_ENABLE_DIV=1` 传至原版 PicoRV32；默认配置三者均为 0。板级 RAM 仍为 4 KiB。

| 配置 | 完整工程 | 烧录产物 | 本地实现报告 |
|---|---|---|---|
| `rv32i` | `vivado/project/mlkem_pynqz2.xpr` | `release/` | `build/reports/` |
| `rv32im_iterative` | `vivado/project_rv32im_iterative/mlkem_pynqz2.xpr` | `release/rv32im_iterative/` | `build/reports/rv32im_iterative/` |

迭代配置另外包含 `sim_cpu` 仿真集，顶层为 `tb_picorv32_rv32im`。两种配置分别保存 XPR 和 VIO XCI，运行结果互不覆盖。

生成工程引用仓库内的源文件。移动或复制工程时应包含整个仓库；换机器后可重新运行 Tcl 创建工程。Git 保存源文件、Tcl、`.xpr` 和同一工程树中的 VIO `.xci` 配置；完整运行目录保存在本机，缓存、运行数据库和日志由 Git 忽略。

首次打开克隆后的 XPR 时，Vivado 可能提示未找到已忽略的缓存和旧运行记录；IP 输出可由 Vivado 重新生成。Tcl 入口会重建固定目录中的工程配置，请先保存自行修改的工程设置；它不修改 `rtl/`、`hls/`、固件或 TB 源码。

## 仿真

```text
vivado -mode batch -source scripts/run.tcl -tclargs core
vivado -mode batch -source scripts/run.tcl -tclargs protocol
vivado -mode batch -source scripts/run.tcl -tclargs board
vivado -mode batch -source scripts/run.tcl -tclargs vio
```

| 模式 | 检查范围 | 测试通过标记 |
|---|---|---|
| `core` | 三组核心算术测试 | `V39-E MANUAL RTL COSIM PASS` |
| `protocol` | 复位、字节写使能、独立 AW/W、反压、忙时访问及算术边界 | `BRAM PROTOCOL PASS` |
| `board` | 固件自检、LED、按钮重新启动 | `PYNQZ2 BOARD SIM PASS` |
| `vio` | 三次复位、独立 256 系数参考计算、周期计数与 VIO 连接 | `BOARD VIO SIM PASS` |

各模式均根据 Tcl 创建所选配置的工程，再选择对应仿真集运行。仿真日志位于对应工程目录的 `mlkem_pynqz2.sim/<simset>/behav/xsim/simulate.log`；运行目录由 Git 忽略。周期断言对应仓库原有加速器 RTL 和预编译固件；重新编译固件后，编译器差异可能改变周期数。

RV32IM 指令仿真与板级回归示例：

```text
vivado -mode batch -source scripts/run.tcl -tclargs cpu firmware/images rv32im_iterative
vivado -mode batch -source scripts/run.tcl -tclargs vio firmware/images rv32im_iterative
```

`cpu` 仅适用于 `rv32im_iterative`，成功标记为 `RV32IM_ISA_PASS tests=4096 pcpi=4096`。TB 在真实 CPU 中执行全部 8 种 M 指令，每种覆盖 512 对操作数，并记录 `rdcycle` 与 PCPI 时间。其指令 ROM 和 native memory 握手仅用于仿真，测得的指令周期不能直接替代板级 AXI/RAM 应用周期。覆盖范围、计时边界和独立运行方式见 [CPU 测试说明](../tb/cpu/README.md)。

## 综合、实现与烧录文件

```text
vivado -mode batch -source scripts/run.tcl -tclargs implement
```

该模式使用 `vivado/project/` 工程，通过 `core`、`protocol`、`board`、`vio` 四组仿真后完成综合、布局布线和 bitstream 生成。匹配的 `mlkem_pynqz2.bit`、`mlkem_pynqz2.ltx` 导出至 `release/` 并纳入 Git；资源、时序、bus-skew 与 DRC 报告保存在 `build/reports/`。完成后执行 `./scripts/update_release_checksums.ps1` 更新产物校验文件。实际结果见 [验证记录](VALIDATION.md)。

构建迭代配置并归档测量证据：

```text
vivado -mode batch -source scripts/run.tcl -tclargs implement firmware/images rv32im_iterative
```

```powershell
./scripts/update_release_checksums.ps1 -CpuConfig rv32im_iterative
./scripts/collect_rv32im_measurements.ps1
```

迭代配置先通过 `cpu` 和原四组仿真，再综合、布局布线并导出独立目录中的 BIT/LTX。采集脚本将仿真结果、指令周期 CSV、实现报告和输入哈希保存至 `results/rv32im_iterative/`；汇总表见 [BENCHMARKS.md](BENCHMARKS.md)。该 transfer 工程保留相同的 RV32I 镜像检查兼容性；软件 NTT 基准使用独立 `cpu_baseline` 工程，官方 KeyGen 使用上述 `mlkem_keygen` 工程，三者的测量边界不同。

连接 PYNQ-Z2 的 JTAG 后，可在 Hardware Manager 中加载同次构建的 BIT/LTX，或显式执行：

```text
vivado -mode batch -source scripts/program_board.tcl
```

**上述烧录命令会配置已连接的开发板。** 它使用 `release/` 的烧录文件；创建工程和实现命令均不会自动调用它。

`program_board.tcl` 仍默认加载原始 RV32I 产物。后续若需烧录 RV32IM 配置，请在 Hardware Manager 中手动选择 `release/rv32im_iterative/` 下同次构建的 BIT 和 LTX。本轮按要求仅完成仿真与实现，未烧录实体板。

固件上电后运行自检。`BTN0` 复位并重新启动系统；成功时 `LED[3:0] = 0101`，即 PASS 与 done 置位，error 与 trap 清零。在 GUI Hardware Manager 中连接并加载 BIT/LTX 后，可在 Tcl Console 运行：

```tcl
source scripts/read_board_vio.tcl
```

该脚本读取 VIO 状态并将快照保存至 `build/hardware/`。本次仓库整理未对实体开发板执行烧录或验收。

## 固件

运行 `./scripts/verify_sources.ps1` 可核对历史清单中的 52 个源码、约束和初始化文件。阶段 2 有 48 项保持原始内容，4 项封装/TB 的 CPU 参数透传变更通过 `docs/source_changes.csv` 中的原始及当前哈希核对；CPU 内核、加速器、固件、约束和原回归断言未修改。

```powershell
./scripts/build_memory_transfer_compare.ps1 -ToolDir 'YOUR_RISCV_BIN_DIRECTORY'
```

也可通过 `RISCV_TOOLCHAIN_BIN` 环境变量指定工具链。脚本以 RV32I/ILP32、`-O2` 编译 `firmware/src/memory_transfer_compare_firmware.c`，使用 `firmware/linker/link.ld`，检查镜像容量、静态 RAM 布局及是否出现 M 扩展指令。输出位于 `build/firmware/`，不会覆盖 `firmware/images/`。

| 镜像 | 传输循环 |
|---|---|
| `transfer_baseline.mem` | 基线 |
| `transfer_write_unroll4.mem` | 写循环展开四次 |
| `transfer_read_unroll4.mem` | 读循环展开四次 |
| `transfer_both_unroll4.mem` | 读写循环均展开四次，默认镜像 |

使用新编译的默认镜像进行仿真：

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio build/firmware
```

静态 RAM 检查不代表已测量运行时最大栈深度。不要仅因新编译结果导致周期断言失败就修改测试期望值，应先核对工具链与功能结果。

## HLS 源码与 C 仿真

在 Vitis 2024.2 环境中，先进入 `hls/`，使配置中的相对路径正确解析：

```text
vitis-run --mode hls --csim --config hls_config.cfg --work_dir ../build/hls_csim
```

独立 C 测试以直接卷积检查三组输入。主文件包含 `mlkem_poly_mul256_v39e_unified_stream_support.cpp`，不要将该支持文件再作为独立编译单元添加。

如需后续重新综合：

```text
v++ --mode hls --config hls_config.cfg --work_dir ../build/hls_synthesis
```

这些命令不替换 `rtl/accelerator/`。现有加速核 RTL 来自 Vitis HLS 2025.2；C 仿真通过不能证明 HLS 2024.2 重新生成的 RTL 与现有快照等价。更新快照需要单独完成 RTL 仿真、协同仿真及实现验证。

2026-09-24 全量执行完成：三组各 145 / 145 条通过，44 个续跑批次均有成功日志与工程证据。已完成的工作区直接运行 `collect_resumed.py --check` 即可核对，不必重建固件或重跑用例。2026-09-25 快速乘法阶段 profiling 也已完成 145 / 145 条，独立证据见 [阶段报告](MLKEM512_PROFILE.md)。
