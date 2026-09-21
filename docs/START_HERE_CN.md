# 从这里开始

这是独立的本地发布候选目录，不是旧工程的快捷方式。原工程、历史实验和原始证据没有移动或删除；目前没有上传 GitHub，也没有选定项目许可证。

## 1. 当前推荐的是哪一版

固定主线为：PYNQ-Z2 板级顶层 + PicoRV32 RV32I + BRAM AXI4-Lite wrapper + 共享运算单元 PolyMul 核心 + 输入/输出循环均展开四次的固件。VIO 仅用于观察状态和计数。

```text
板载 125 MHz 时钟 -> MMCM 100 MHz
                       |
PicoRV32 <-> 4 KiB 程序/数据 RAM
    |
    +-- AXI4-Lite -> 地址译码 -> BRAM wrapper -> PolyMul 核心
    |
    +-- 状态/周期寄存器 -> LED / 只读 VIO
```

直观地说，CPU 执行固件、搬入两个多项式、通知加速器开始、等待完成，再读回和核对结果。wrapper 负责让 CPU 和核心按规则访问输入/输出存储；它不是另一份 NTT 算法。计算目标是模 3329、模 `x^256+1` 的两个 256 系数多项式乘法，不是完整 ML-KEM。

## 2. 怎么打开和运行

最推荐先使用 Vivado 命令行，从项目根目录执行：

```text
vivado -mode batch -source scripts/run.tcl -tclargs vio
```

脚本会建立 `build/vio_<时间戳>_<进程号>/mlkem.xpr` 并运行仿真。已有本次迁移验证工程的位置见 [迁移验证记录](MIGRATION_VALIDATION.md)，可直接在 Vivado 的 **File > Project > Open** 中选择该 `.xpr`。

不要把 `.v`、`.sv`、`.tcl`、`.cfg` 当成 Vivado 工程打开。它们分别是 RTL、仿真代码、脚本和 HLS 配置。GitHub 候选文件保留这些源文件及建工程脚本，而不依赖某台电脑已经生成的工程缓存。

成功标志为 `BOARD VIO SIM PASS` 和 `CANDIDATE_REGRESSION_PASS`，不是只看波形有变化。此仿真不要求连接板子。

HLS 入口是 `hls/hls_config.cfg`，顶层函数仍为 `mlkem_poly_mul256_v39e_true_one_dsp`。为不破坏模块引用、自动生成 RTL 和层次观察器，这次只整理目录，不批量重命名历史模块。

其他命令、固件重建和上板准备见 [BUILD.md](BUILD.md)。本次没有重新下载到板子。

## 3. 核心文件用途

| 路径 | 专业作用 | 直观理解 |
|---|---|---|
| `rtl/board/mlkem_polymul_pynqz2_top.v` | 板级时钟、复位、LED、可选 VIO 和系统例化 | 连接板子引脚的最外层 |
| `rtl/system/mlkem_polymul_rv32i_profile_top.v` | CPU、4 KiB RAM、地址译码、加速器、计数输出 | 把 CPU、内存和加速器接在一起 |
| `rtl/cpu/picorv32.v` | 第三方 PicoRV32 CPU 及 AXI 适配逻辑 | 执行固件指令 |
| `rtl/axi/mlkem_polymul_axi_wrapper.v` | 推荐的 BRAM wrapper，处理 AXI 寄存器和存储端口所有权 | 接收 CPU 命令，协调谁可以访问 A/B/OUT |
| `rtl/axi/mlkem_coeff_tdp_ram.v` | wrapper 使用的双端口系数 RAM | 存放输入和结果 |
| `rtl/accelerator/mlkem_poly_mul256_v39e_true_one_dsp.v` | HLS 生成的核心顶层 | 安排完整乘法计算链 |
| `hls/src/mlkem_poly_mul256_v39e_true_one_dsp.cpp` | 当前 HLS 核心源码 | 核心设计的 C++ 描述 |
| `hls/src/mlkem_poly_mul256_v39e_unified_stream_support.cpp` | 被主源码 include 的运算/流处理支持实现 | 主文件必需的辅助逻辑，不要另设为 top |
| `hls/tb/tb_mlkem_poly_mul256_v39e.cpp` | 独立朴素负循环卷积 oracle | 用另一种算法检查结果，而非复用 DUT 算法 |
| `hls/hls_config.cfg` | 器件、时钟、顶层、源码和测试入口 | HLS 的构建配方 |

`rtl/accelerator/` 的生成模块需要整体保留：`batch39d` 调用共享流水运算；`issue39d` 发出任务；`pe39c` 计算；`write39d` 写回；`Pipeline_load/save/pack` 搬运或重排数据；`ant/bnt/ping/bm` 等 RAM 模块存中间结果；`fifo`、`start_for` 和 `flow_control` 协调流水线；`mul/sub/sparsemux` 是运算和选择逻辑；`zetas*.dat` 是旋转因子 ROM 初始化数据。文件很多不意味着每个都是独立设计方案，也不应因名字陌生而删除。

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

## 5. 这次新增或调整的管理文件

| 文件 | 作用 |
|---|---|
| `README.md` | 英文首页，范围、入口和目录总览 |
| `docs/START_HERE_CN.md` | 本中文文件说明 |
| `docs/BUILD.md` | 工具前提和复现命令 |
| `docs/RESULTS.md` | 历史性能与资源结果，以及不能越过的结论边界 |
| `docs/MIGRATION_VALIDATION.md` | 本次实际重建和仿真的结果、失败与未验证项 |
| `docs/architecture.svg` | 从原工程复制的架构图；不是新增测量证据 |
| `scripts/run.tcl` | 新建唯一推荐 Vivado 入口，全部源码从新目录选取，拒绝外部工程源码 |
| `scripts/build_memory_transfer_compare.ps1` | 原构建脚本改为参数化工具路径，不改变固件算法 |
| `scripts/read_board_vio.tcl` | 原读板脚本，采样输出改存 `build/hardware/` |
| `.gitignore` | 排除可重建工程、二进制、缓存等；有意保留 evidence 日志 |
| `.gitattributes` | 禁止 Git 自动转换换行，保证下载后的文件字节与 SHA256 清单一致 |
| `SOURCE_MANIFEST.csv` | 最初导入的逐文件 SHA256 和来源类别 |
| `FINAL_MANIFEST.csv` | 整理后候选文件的 SHA256；不包含本机 build 缓存 |
| `evidence/REDACTION_MANIFEST.csv` | 证据副本脱敏前后的 SHA256，便于追溯 |
| `THIRD_PARTY_NOTICES.md` | 第三方声明、许可证和公开发布前待确认的问题 |
| `experiments/README.md` | 说明历史对照不属于默认入口 |

`experiments/register_wrapper/` 保留旧寄存器 wrapper 和原六阶段/输入准备/循环对照 testbench。它与 `rtl/axi/` 存在同名模块，不能一起加入同一工程。旧版本移入候选目录的隔离区域，不代表原工程文件被移动。

`evidence/historical/` 保存精选历史利用率、时序、DRC、仿真和一次实板 VIO 数值快照。`evidence/migration/` 保存本次整理后的回归日志。两者分开，避免把旧报告冒充本次结果；仅对副本中的本地路径和主机名脱敏。

`build/` 和 `firmware/build/` 是本机可重建产物，可用于自己打开工程和查日志，但不应整目录上传。所有候选文件的精确清单见 `FINAL_MANIFEST.csv`。

父目录中的 `prepare_mlkem_release.ps1` 是本次使用的一次性复制整理工具，不属于候选仓库，也不参与后续构建；目标目录已存在时它会拒绝覆盖。正常使用只需要当前新项目目录及已安装的开发工具。

## 6. 发布前仍要做什么

目前主线 RTL 系统可以从新目录建立并仿真。历史实验源码的保留不等于每个旧实验都已在新目录重跑。HLS 源码 C 仿真、重新综合生成 RTL、C/RTL 协同仿真、布局布线、实板执行是不同层级，不能互相代替。

公开前需要确认实习/合作项目的公开权限、选择自己的代码许可证，并审查第三方及生成代码的再分发条件。本次没有替你作出这些决定。
