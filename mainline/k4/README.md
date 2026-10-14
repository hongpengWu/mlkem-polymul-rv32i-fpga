# K4 主线：源码与复现入口

`default` 分支集中维护 ML-KEM-1024 的 PicoRV32 + Keccak + PS–PL 系统。
这次整理改变目录和运行入口，不改变算法、RTL 和官方向量。

```text
mainline/k4/
├── flow.tcl         HLS、CPU集成测试和独立PL实现
├── bd_axi.tcl       PS–PL Block Design、AXI验证和overlay实现
├── hls/             加速器C++、HLS测试和报告工具
├── rtl/             CPU/RAM/加速器连接、MMIO、AXI和板级顶层
├── firmware/        RISC-V固件、Keccak驱动和链接脚本
├── tb/              系统、AXI、板级仿真测试平台
├── constraints/     系统和板级时序/引脚约束
├── pynq/            Notebook和Python驱动源码
└── scripts/         固件构建、数据准备、证据核验等Python辅助工具
```

共用 CPU 位于 `../../rtl/cpu/`；标准 C 库在 `../../third_party/`；官方向量在
`../../vectors/`；共用启动代码及 CPU-only 固件在 `../../firmware/`。
共用组件只维护一份，不复制到主线。

## 工具与路径

使用 Vivado / Vitis HLS **2024.2**、Python 3 和 Tcl；目标器件为 PYNQ-Z2 的
`xc7z020clg400-1`。RISC-V 固件使用 `riscv64-unknown-elf` 工具链。
从已配置 AMD 工具环境的终端运行，或者设置：

- `PQC_VIVADO`、`PQC_VITIS_HLS`：对应可执行文件。
- `PQC_RISCV_TOOL_DIR`：RISC-V 编译器所在目录。
- `PQC_BOARD_DIR`：PYNQ-Z2 板卡文件目录（含 `board.xml`、`preset.xml`、`part0_pins.xml`）。

工具安装目录属于使用者环境，源码不固定盘符。
项目内路径以脚本确定的仓库根目录解析，不依赖终端所在目录。
默认构建区为仓库 `build/k4/`；AMD 工具若受长路径限制，可用 `FLOW_SHORT_ROOT` /
`HLS_BUILD_ROOT` / `BD_SHORT_ROOT` 指定短构建目录。源码仍维护在本目录。
不要将旧生成工程复制回源码目录。

## 两个 Tcl 入口

从仓库根目录运行；从其他目录运行时，只需给入口 Tcl 的正确路径：

```powershell
tclsh mainline/k4/flow.tcl
vivado -mode batch -source mainline/k4/bd_axi.tcl
```

先看顶部 0/1 开关。主流程保留 `CSIM / CSYNTH / COSIM / VIVADO_SYN / VIVADO_IMPL / EXPORT`，
并提供 CPU smoke、KAT 子集/全量及独立板级阶段。BD 使用
`PREPARE / SIM / CREATE_BD / SYNTH / IMPL / EXPORT`。
`CHECK_ONLY=1` 用于路径/配置预检；实际执行需设为 0。
环境变量 `FLOW_<名称>`、`BD_<名称>` 可覆盖对应选项。

先完成 HLS 功能验证，再用 `FLOW_HLS_RUN` 指向成功运行目录；也可以通过
`PQC_HLS_RUN` 给 Python 辅助工具选择该目录。选择时核对源码、测试、配置和运行证据，
不直接依赖开发者旧电脑上的绝对路径；历史报告中的原始路径只作为溯源信息保留。

独立 HLS 的 `export_design -flow impl` 只实现 HLS IP；完整系统实现由系统/BD 阶段负责。
工具运行中自动生成的 Tcl 是构建产物，不是第三个手写入口。

## 测试与结果

日常使用组件 smoke 和官方索引 0、1、115 的子集；`FULL_KAT=1` 才执行 145 条完整回归。
目录整理的验证与历史全量验收分开记录。只启动成功或完成 elaboration，不能记成测试 PASS。
很长的路径检查运行可在已有输入加载和仿真启动证据后停止，结果须标明未完成。

- [results/reorganization](../../results/reorganization/)：本次迁移映射和验证记录。
- [results/keccak_cpu](../../results/keccak_cpu/)：历史核心、板级、PS–PL 证据。
- [results/hls/mlkem1024_keccak](../../results/hls/mlkem1024_keccak/)：历史 HLS 性能证据。
- [release/mlkem1024_pynq](../../release/mlkem1024_pynq/)：固定部署包。

上述链接均相对于主线目录解析。部署包中的 `.bit/.hwh` 必须配套使用，
其中 manifest 记录的历史构建路径不因为迁移而改写。

已冻结的核心 145/145 和 3.8028×是历史 RTL 证据；PS–PL overlay 的实板验证状态见
[项目进度](../../docs/PROJECT_STATUS.md)。迁移验证不增加算法覆盖或实板完成度。
