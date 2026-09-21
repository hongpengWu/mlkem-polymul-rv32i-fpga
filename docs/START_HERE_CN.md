# 项目说明与文件索引

本仓库实现面向 PYNQ-Z2 的 ML-KEM 多项式乘法加速系统，包含 HLS 源码、生成 RTL、PicoRV32 固件、仿真测试及实验记录。代码已公开托管于 [GitHub](https://github.com/yttting/mlkem-polymul-rv32i-fpga)。项目级许可证尚未确定，第三方组件的声明及使用条件见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

## 1. 系统配置

默认配置采用 PicoRV32 RV32I 处理器、BRAM AXI4-Lite wrapper 和共享运算单元 PolyMul 核心。固件的输入写入与输出读取循环均采用四次展开（mode 3）。系统运行于 Zynq 的可编程逻辑（PL），不使用 ARM 处理系统（PS）；可选的 Virtual Input/Output（VIO）模块用于只读调试。

```text
时钟：板载 125 MHz -> MMCM + BUFG -> 系统 100 MHz

互连：PicoRV32 -> AXI4-Lite 地址译码
                    +-- 4 KiB 程序/数据 RAM
                    +-- BRAM wrapper <-> PolyMul 核心
                    +-- 状态/周期寄存器 -> LED / 只读 VIO
```

CPU 将本地 RAM 中的两个输入多项式写入加速器，写启动寄存器，轮询完成状态，随后读回结果。BRAM wrapper 实现控制寄存器、AXI 事务处理和 CPU/核心之间的存储端口仲裁。

计算范围为环 `Z_3329[x]/(x^256+1)` 中两个 256 系数多项式的乘法，执行顺序为 `FNTT(A) -> FNTT(B) -> BaseMul -> INTT -> FinalScale`。本仓库不包含完整 ML-KEM 的密钥生成、封装和解封装流程。

## 2. 工程构建与仿真

安装 Vivado 2025.2 及 Zynq-7000 器件支持后，在已配置 Vivado 环境的终端中进入仓库根目录，执行：

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio
```

脚本在本地生成 `build/vio_<时间戳>_<进程号>/mlkem.xpr` 并运行仿真。生成后可通过 Vivado 的 **File > Project > Open** 打开该 `.xpr`。仓库不包含预生成的 `.xpr`，首次克隆后需要先执行构建脚本。

`.v`、`.sv`、`.tcl` 和 `.cfg` 分别用于 RTL、SystemVerilog 测试、自动化脚本和 HLS 配置，不是 Vivado 工程文件。

正常结束时，日志包含 `BOARD VIO SIM PASS` 和 `CANDIDATE_REGRESSION_PASS`，且无错误或超时。该测试重复复位三次，对同一组确定性输入的 256 个输出系数进行独立参考计算检查，同时验证周期计数和 VIO 连接。仿真不需要连接开发板。

HLS 配置文件为 `hls/hls_config.cfg`，顶层函数为 `mlkem_poly_mul256_v39e_true_one_dsp`。源码和生成 RTL 保留历史模块名，以维持模块引用及层次观察器的兼容性。

固件重建、HLS C 仿真及 implementation 命令见 [BUILD.md](BUILD.md)。已执行的验证及其范围见 [迁移验证记录](MIGRATION_VALIDATION.md)。

## 3. 核心文件用途

| 路径 | 职责 |
|---|---|
| `rtl/board/mlkem_polymul_pynqz2_top.v` | 板级顶层，实例化时钟管理、复位同步、系统、LED 和可选 VIO |
| `rtl/system/mlkem_polymul_rv32i_profile_top.v` | 集成 CPU、4 KiB RAM、地址译码、加速器及状态寄存器 |
| `rtl/cpu/picorv32.v` | 第三方 PicoRV32 CPU 及 AXI 适配逻辑 |
| `rtl/axi/mlkem_polymul_axi_wrapper.v` | AXI 控制接口、A/B/OUT 存储访问和端口仲裁 |
| `rtl/axi/mlkem_coeff_tdp_ram.v` | 256 x 16-bit 双端口 RAM，支持同步读写及字节写使能 |
| `rtl/accelerator/mlkem_poly_mul256_v39e_true_one_dsp.v` | HLS 生成的 PolyMul 核心顶层 |
| `hls/src/mlkem_poly_mul256_v39e_true_one_dsp.cpp` | PolyMul 核心的 HLS C++ 实现 |
| `hls/src/mlkem_poly_mul256_v39e_unified_stream_support.cpp` | 由主源码 include 的运算与流处理实现，不作为独立翻译单元编译 |
| `hls/tb/tb_mlkem_poly_mul256_v39e.cpp` | 采用独立 O(N^2) 负循环卷积的 C 功能测试 |
| `hls/hls_config.cfg` | HLS 器件、时钟、顶层函数、源码和 testbench 配置 |

`rtl/accelerator/` 包含一个核心的完整生成模块集合。`batch39d` 调用共享流水运算，`issue39d` 发出任务，`pe39c` 计算，`write39d` 写回；`Pipeline_load/save/pack` 负责搬运和重排。`ant/bnt/ping/bm` 等模块存储中间结果，`fifo/start_for/flow_control` 协调流水线，`mul/sub/sparsemux` 实现运算和选择逻辑。名称含 `zetas` 的 `.dat` 文件提供旋转因子 ROM 初值。构建脚本将这些模块作为一个整体加入工程。

## 4. 固件、测试和约束

| 文件 | 用途及是否为主线 |
|---|---|
| `firmware/memory_transfer_compare_firmware.c` | 当前主线固件；四种循环模式，默认板级镜像使用 mode 3 |
| `firmware/expected_words.h` | 固件核对输出使用的打包参考结果；系统仿真另有独立 oracle |
| `firmware/link.ld` | 4 KiB 程序/数据 RAM 的链接布局和静态空间约束 |
| `firmware/prebuilt/transfer_*.mem` | 四种固件的归档文本镜像，用于复现固定周期 |
| `firmware/profile_firmware.c`、`prebuilt/profile_firmware.mem` | 之前的六阶段测量，保留作参考 |
| `firmware/prepare_compare_firmware.c`、`prebuilt/prepare_*.mem` | 本地缓冲与直接生成输入的对照实验 |
| `firmware/software_polymul.c`、`software_profile.c`、`software_start.S`、`prebuilt/software_o2.mem` | 纯软件计算、计时、启动代码及归档镜像；不等于当前板级加速固件 |
| `sim/profile/tb_pynqz2_profile_vio.sv` | 推荐回归：三次复位、独立检查 256 系数、固定周期和 VIO 接线 |
| `sim/profile/tb_pynqz2_bram_board.sv` | 不带 VIO 的 LED/复位检查，覆盖面比推荐回归小 |
| `sim/profile/tb_bram_wrapper_protocol.sv` | AXI 字节使能、分离 AW/W、背压、忙时访问、重复执行与环边界测试 |
| `sim/profile/tb_mlkem_bram_transfer.sv` | BRAM 版四种搬运循环实验；不是默认回归入口 |
| `sim/profile/tb_software_baseline.sv`、`test_software_polymul.c` | 软件基线 RTL 测试和宿主 C 功能测试；不是默认回归入口 |
| `sim/core/tb_v39e_true_one_dsp.sv` | 裸核心 RTL 功能/周期测试源码；不是默认回归入口 |
| `sim/observer/mlkem_core_cycle_observer.sv` | 观察核心批次、搬运和状态机的时间分解；依赖当前 RTL 层次名称 |
| `sim/observer/mlkem_axi_profile_observer.sv` | 观察 AXI 请求/响应和访问间隔；保留实验源码，默认 VIO 回归未接入 |
| `constraints/pynq_z2_board.xdc` | PYNQ-Z2 引脚、电压、125 MHz 输入时钟 |
| `constraints/pynqz2_bram_reset.xdc` | 按钮异步复位及 LED 相关的板级时序例外 |
| `constraints/system_ooc_10ns.xdc`、`v39e_ooc_10ns.xdc` | 历史系统/裸核心 OOC 的 10 ns 约束，不加入板级默认入口 |

## 5. 构建脚本与文档

| 文件 | 作用 |
|---|---|
| `README.md` | 英文首页，范围、入口和目录总览 |
| `docs/START_HERE_CN.md` | 本中文文件说明 |
| `docs/BUILD.md` | 工具前提和复现命令 |
| `docs/RESULTS.md` | 性能、资源、测量范围及对应日志 |
| `docs/MIGRATION_VALIDATION.md` | 2026-09-21 迁移回归的结果、环境问题与未验证项 |
| `docs/architecture.svg` | 系统及核心架构图 |
| `scripts/run.tcl` | Vivado 建工程和回归入口；检查工程源码均位于仓库目录内 |
| `scripts/build_memory_transfer_compare.ps1` | 构建四种搬运循环固件，支持指定 RISC-V 工具链目录 |
| `scripts/read_board_vio.tcl` | 读取实板 VIO，采样结果保存到 `build/hardware/` |
| `.gitignore` | 排除可重建工程、二进制、缓存等；有意保留 evidence 日志 |
| `.gitattributes` | 禁止 Git 自动转换换行，保证下载后的文件字节与 SHA256 清单一致 |
| `SOURCE_MANIFEST.csv` | 最初导入的逐文件 SHA256 和来源类别 |
| `FINAL_MANIFEST.csv` | 当前版本文件的 SHA256；不包含清单自身和构建产物 |
| `evidence/REDACTION_MANIFEST.csv` | 证据副本脱敏前后的 SHA256，便于追溯 |
| `THIRD_PARTY_NOTICES.md` | 第三方声明、许可状态和代码来源待核实项 |
| `experiments/README.md` | 说明历史对照不属于默认入口 |

`experiments/register_wrapper/` 保留寄存器实现的 wrapper，以及六阶段计时、输入准备和循环展开实验的 testbench。它与 `rtl/axi/` 定义同名模块，不能同时编译。默认构建脚本仅使用 `rtl/axi/`。

`evidence/historical/` 保存归档的利用率、时序、DRC、仿真报告和一次实板 VIO 数值快照。`evidence/migration/` 保存 2026-09-21 的迁移回归日志。报告副本中的本地路径和主机名已脱敏，测量数值保持不变。

`build/` 和 `firmware/build/` 存放本地构建产物，已由 `.gitignore` 排除。仓库文件清单见 `FINAL_MANIFEST.csv`。

## 6. 验证范围与许可

默认配置已完成迁移后的固件重建、RTL 系统回归和 HLS C 仿真。归档的所有对照实验未逐一重跑；重新生成 RTL 后的协同仿真、布局布线和实板测试也不属于该次迁移验证。资源与实板数值的来源详见 [RESULTS.md](RESULTS.md)。

维护者已确认项目允许公开托管。项目级许可证尚未确定，代码公开不构成对所有文件的统一再分发授权；第三方组件仍适用各自的许可条件。
