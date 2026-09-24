# 目录与维护规则

工程按硬件、固件、验证和工具入口组织。默认 RV32I 与 RV32IM 迭代乘法配置分别保存工程和烧录产物；工具缓存独立于主线源文件，纳入 Git 的测量证据集中在 `results/`。

```text
mlkem-polymul-rv32i-fpga/
├── rtl/
│   ├── accelerator/       HLS 生成的 Verilog 与 ROM 数据，整体维护
│   ├── axi/               AXI4-Lite wrapper 与系数双口 RAM
│   ├── benchmark/         CPU-only 系统、16 KiB RAM 与板级封装
│   ├── board/             PYNQ-Z2 顶层、时钟、复位、LED 与 VIO 连接
│   ├── cpu/               PicoRV32
│   └── system/            CPU、固件 RAM、总线、加速器与监测寄存器
├── constraints/           两份板级 XDC
├── hls/
│   ├── src/               HLS C++ 算法及支持代码
│   ├── tb/                独立 C 算术测试
│   └── hls_config.cfg     器件、时钟、顶层及文件配置
├── firmware/
│   ├── src/               transfer 固件
│   ├── cpu_baseline/      CPU-only 软件多项式乘法 baseline 源码、启动文件与链接脚本
│   ├── include/           expected_words.h
│   ├── linker/            link.ld
│   └── images/            transfer 镜像及 cpu_baseline/ 下的 RV32I/RV32IM 镜像
├── tb/
│   ├── cpu/               RV32IM 八类 M 指令验证与计时
│   ├── software/          CPU-only 多项式输入、oracle 与 PicoRV32 系统仿真
│   ├── core/              加速核独立 RTL 测试
│   ├── board/             无 VIO 与带 VIO 的板级测试
│   ├── protocol/          AXI/BRAM wrapper 协议测试
│   └── monitors/          核心周期监测器
├── vivado/
│   ├── project.tcl        统一器件、源文件、约束、IP 与仿真集配置
│   ├── project/           默认 RV32I 完整工程，跟踪 .xpr 与 VIO .xci
│   ├── project_rv32im_iterative/  迭代乘法完整工程，跟踪 .xpr 与 VIO .xci
│   ├── cpu_baseline_rv32i/       RV32I CPU-only 仿真工程，跟踪 .xpr 与固件镜像
│   ├── cpu_baseline_rv32im_iterative/  迭代乘法 CPU-only 工程
│   └── cpu_baseline_rv32im_fast/      快速乘法 CPU-only 工程
├── scripts/
│   ├── run.tcl            创建工程、仿真与实现入口
│   ├── build_memory_transfer_compare.ps1
│   ├── verify_sources.ps1 / update_release_checksums.ps1
│   ├── collect_rv32im_measurements.ps1  仿真与实现证据采集
│   ├── cpu_baseline/      生成 baseline 镜像、运行三组 XSim 与收集结果
│   ├── program_board.tcl  显式 JTAG 烧录入口
│   ├── read_board_vio.tcl  只读状态采集
│   └── kat/                ACVP JSON 检查与主机参考回归入口
├── vectors/
│   └── official_kat/acvp/  FIPS 203/ACVP 官方 prompt/expected 向量、来源和哈希
├── docs/                  使用说明、竞赛路线图、结构图、验证记录、BENCHMARKS.md 与源码哈希
├── results/               纳入 Git 的测量证据与哈希
│   ├── rv32i_baseline/    原始 RV32I 实现报告
│   ├── rv32im_iterative/  指令/系统仿真、实现报告、输入及结果哈希
│   ├── cpu_baseline/      RV32I、RV32IM 迭代与 RV32IM 快速软件对照结果
│   └── official_reference/ 主机端 ACVP 回归日志和运行元数据
├── release/               默认 RV32I 的 BIT、匹配 LTX 与校验文件
│   └── rv32im_iterative/  RV32IM 迭代配置的独立烧录产物
└── build/                 本地生成目录，Git 忽略
    ├── reports/           默认报告及 rv32im_iterative/ 配置报告
    ├── firmware/          ELF、BIN、MEM、反汇编与布局报告
    ├── hls_csim/          HLS C 仿真输出
    ├── hls_synthesis/     可选 HLS 综合输出
    └── hardware/          VIO 读回快照
```

CPU-only 工程的源码与测试输入仍由 `scripts/cpu_baseline/run.tcl` 从仓库根目录引用；Vivado 目录只保存可打开的 `.xpr` 及对应 `cpu_baseline.mem`。`cpu_baseline.sim/`、`cpu_baseline.cache/`、`cpu_baseline.runs/` 等目录属于本地生成物，不纳入版本库。

`COMPETITION_ROADMAP.md` 只记录目标、阶段门、创新主线和证据要求；实际测量数据归档在 `results/` 并登记到 `BENCHMARKS.md`，不把规划数字当作实测结果。

`vectors/official_kat/` 保存标准输入和预期结果，`scripts/kat/` 只负责结构检查、哈希复核和
主机参考实现回归。官方 KAT 通过不等于 PicoRV32 或 FPGA 加速器已经通过；后两者必须在
后续独立的固件和 CPU+加速器阶段逐字节检查。

## 源码一致性

- 初始目录整理保持原有 HDL、HLS、固件、TB、初始化数据和板级约束内容，模块名及文件名未改名。阶段 2 仅在系统/板级封装及两个板级 TB 中增加 CPU 配置参数透传，默认值和原回归断言不变；PicoRV32 内核、加速器、HLS、固件与约束未改动。
- `rtl/accelerator/` 的 Verilog 和 `.dat` 属于同一生成快照，应整体保留。ROM 和固件采用文件名初始化，工程配置负责将其加入 Vivado 的源文件集合。
- `v39e` 等原有名称涉及模块层次与监测器引用，保留这些名称可避免改变设计连接关系。
- 默认板级镜像始终为 `transfer_both_unroll4.mem`。其他三种 transfer 镜像保留用于复现与比较，不自动替换默认镜像。
- `vivado/project.tcl` 是工程配置入口；需要调整源文件路径时先修改 Tcl，再重新生成本地工程。

## 保留范围

保留最终板级实现、HLS 源码、transfer 固件、CPU-only 软件基线、CPU 指令及系统/核心仿真、板级约束及构建/烧录工具。旧 register wrapper 实验、旧软件基线、输入准备对比、历史 OOC 约束和无关归档报告不属于当前维护目录；其历史版本仍可通过 Git 查询。本轮测量所需的原始日志与实现报告保存于 `results/`，用于核对 [性能数据表](BENCHMARKS.md)，不作为工程输入。

版本库同时保存重建工程的输入、可直接打开的 `.xpr`、VIO `.xci` 和烧录文件。本机保留完整生成的工程树；`.cache`、`.runs`、`.sim` 等可生成内容不提交。

`docs/source_integrity.csv` 保留初始整理时的 52 项 SHA-256；`docs/source_changes.csv` 明确记录其中 4 项 CPU 配置透传变更的原始哈希、当前哈希和原因。`scripts/verify_sources.ps1` 同时核对两份清单，当前应报告 48 项原始文件不变、4 项配置变更通过。新增 CPU TB 与工程脚本等构建输入的哈希另记录在 `results/rv32im_iterative/build_inputs.csv`。
