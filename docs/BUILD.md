# 构建、仿真与实现

当前仓库的可复现入口分为四类：CPU-only Vivado 工程、ML-KEM 官方软件回归、新 HLS，
以及独立的 BaseMul MMIO/BRAM/PYNQ-Z2 验证工程。旧完整加速器的根级
`run.tcl/project.tcl`、板级烧录脚本和 transfer 工程已经删除。

## 工具版本

- Vivado 2024.2，器件 `xc7z020clg400-1`
- Vitis HLS 2024.2
- Windows PowerShell、Python 3
- RISC-V GCC 工具链（路径通过 `RISCV_TOOLCHAIN_BIN` 或脚本参数配置）

## K4 主线统一入口

日常迭代从一个Tcl入口运行，顶部开关选择HLS、smoke、官方子集和系统实现：

```powershell
D:/Tech/Library/bin/tclsh.exe scripts/mlkem1024_keccak/run_flow.tcl
```

默认`KAT_SUBSET=1`、`FULL_KAT=0`、`COLLECT=1`，仅执行索引0、1、115；
同版本已完成的记录核验后跳过。HLS开关包含`CSIM/CSYNTH/COSIM/VIVADO_SYN/VIVADO_IMPL/EXPORT`；
`SMOKE=1`默认先编译组件固件，`IMPLEMENTATION=1`只实现当前加速组，不重复冻结CPU基线。
每次改RTL后换`CANDIDATE`，否则哈希检查拒绝混合版本；结果位于
`results/keccak_cpu/candidates/<CANDIDATE>/kat/`。底层Python负责固件、冻结哈希、断点与汇总，
既有Tcl负责EDA阶段；主线完成后统一精简重复入口。

实现工具异常退出但已有完整`synth.dcp`时，可设置`RESUME_SYNTH`为原运行目录，
关闭KAT、开启`IMPLEMENTATION`，从综合检查点恢复布局布线。入口核验原输入和配置，
在新目录保留恢复来源及哈希；原失败证据不覆盖。时序报告在最终检查点之前保存。

最终候选才设`FULL_KAT=1`，顺序补齐145条，每批最多8条。子集汇总状态为PARTIAL，
不能当作全量验收。HLS生成的新核必须完成验证与选择，入口不会自动替换`HLS_RUN`所指向的已验证核。
默认复用已构建KAT固件；软件源码改变时需独立保留原固件/记录并重新构建，不能混入原结果。

已冻结核心版本`timing_decode_v3`的145条已完成，只读复核（不代表新PS–PL overlay覆盖）：

```powershell
python scripts/mlkem1024_keccak/collect_kat.py --results-dir results/keccak_cpu/candidates/timing_decode_v3/kat
```

历史完整145条证据只读核验：

```powershell
python scripts/mlkem1024_keccak/collect_kat.py
```

该历史结果在`results/keccak_cpu/kat/`，原始冻结工程在`E:/hls/k4kat/`。
当前RTL修改不改写历史证据。实现原始setup/hold失败仍保留，内部寄存器时序另列；
系统OOC不代替板级签核。HLS生成RTL/IP、DCP和缓存不进入Git。

板级仿真通过后，如只需修正约束或物理实现，可设置`RESUME_BOARD`为原运行目录，
同时使用`BOARD_SIM=0`、`BOARD_IMPL=1`、`BOARD_BITSTREAM=1`。恢复入口会核对manifest、
结果、91项冻结输入、仿真日志和routed DCP的SHA-256；RTL、HLS、固件或TB变化时拒绝复用。
新目录记录恢复来源并重新执行签核门禁，原失败证据保持不变。

## K4 PS–PL / Jupyter入口

当前部署包：`release/mlkem1024_pynq/`；项目：
`E:/hls/k4pynq/20261005_psaxi06/project/k4_pynq.xpr`。
最终物理设计保存在同批次`routed.dcp`，包含局部布局修复；查看最终实现时打开该DCP。
100 MHz物理签核和包内哈希校验已通过，新overlay尚未上板。

独立3例自检bitstream已有用户报告的LED0 PASS及BTN0复位后恢复；
该观察不包含PS装载、结果读回或全量145例。交互式overlay使用独立的
`scripts/mlkem1024_keccak/vivado_bd.tcl`。该Tcl参考Prompt3的PS/AXI、统一时钟复位、
地址核验和配套`.bit/.hwh`导出方式，使用实际PYNQ-Z2的`xc7z020clg400-1`和已安装板卡preset。

当前断点：`20261004_psaxi02`实际执行的AXI协议检查及官方索引0、1、115三例已PASS。
`20261004_psaxi04`因复位极性/辅助复位接线与GP0接口元数据问题拒绝作为发布候选；
保留其诊断证据，下一步使用修正后的`20261004_psaxi05`重新实现。run05尚无成功结论，
新overlay尚未上板验证；旧核心145/145与3.8028×只作为历史RTL证据。

```powershell
E:/Xilinx/Vivado/2024.2/bin/vivado.bat -mode batch -notrace -source scripts/mlkem1024_keccak/vivado_bd.tcl
```

顶部`PREPARE/SIM/CREATE_BD/SYNTH/IMPL/EXPORT`为0/1开关，默认全开；环境变量`BD_<开关名>`
可覆盖。8个工作线程；运行工程位于`E:/hls/k4pynq/<批次>/project/k4_pynq.xpr`。
这些是PS–PL独立入口的开关；原`run_flow.tcl`继续管理核心/HLS回归与独立PL自检流程。
`PREPARE`编译独立`--ps`固件并冻结RTL、HLS、固件、测试和官方向量；不会重跑旧145条回归。
`SIM`检查AXI握手/错误响应/复位和三条官方记录。综合与实现必须通过时序、路由、DRC，
并验证生成BD的复位极性、时钟与地址连接，才允许发布部署包。

已通过的仿真可通过`BD_REUSE_SIM`复用：设置为原运行目录并设`BD_SIM=0`；入口逐项核对
RTL/HLS/固件/TB/fixture哈希，保留来源。修改这些输入后必须重新仿真。

仅通过门禁后发布到固定目录`release/mlkem1024_pynq/`，不建立多个并列部署目录。
包内包含配套`k4_accel.bit/.hwh`、
`mlkem1024.py`、`mlkem1024.ipynb`、`kat_vectors.json`和`release_manifest.json`。
打开包内`README.txt`可查看该版本准确的XPR位置。整个目录上传到
`/home/xilinx/jupyter_notebooks/mlkem1024/`，在Jupyter打开`mlkem1024.ipynb`。
生成的大文件与EDA工程不进入Git；证据保存在`results/keccak_cpu/pynq/<批次>/`。

BD结构是PS7 GP0→AXI互联→PicoRV32系统的AXI-Lite包装层，统一FCLK0 100 MHz与
`proc_sys_reset`。PicoRV32继续执行ML-KEM，Keccak由PL硬件计算；ARM只装载、校验和显示。

| PS物理地址 / 核内地址 | 用途 |
|---|---|
| `0x40000000..0x4001ffff` / `0x00000..0x1ffff` | 128 KiB程序RAM，双口访问；CPU复位时PS可写 |
| `0x40010000` / `0x10000` | 8 KiB单例输入窗口 |
| `0x40012000` / `0x12000` | 8 KiB结果窗口，预期结果只保留在PS |
| `0x40020000/04` | 硬件ID `0x4b344158` / ABI版本1 |
| `0x40020008` | CONTROL bit0：0复位、1运行 |
| `0x4002000c/10` | 完成/错误状态 / CPU trap |
| `0x40020014/18` | 100,000,000 Hz / RAM字节数 |
| `0x40020040..6f` | 12项固件debug/profile字，API周期在`0x4002004c` |
| `0x40020080..8f` | HLS启动、busy周期、缓冲写/读计数 |

每条用例按“复位→装入输入→启动→读结果→PS逐字节校验”运行。Notebook默认3例，
全量145需显式启用；只有145个唯一索引全部匹配才记全量通过。API周期、装载/读回耗时和
Python总耗时分别记录。页面中的CPU-only值属于历史RTL参考，不能冒充现场软件基线或实板加速比。
新AXI固件/双口RAM属于独立候选，旧核心145/145不转记为新overlay的完整硬件覆盖。
新overlay的LED0表示单例执行/结果传输完成；官方PASS以Notebook逐字节校验为准。
LED1表示固件错误或trap，LED2表示运行，LED3表示trap。

板卡preset中的DDR DQS负偏斜会触发PSU-1..4警告，原始报告保留，未擅自改为零。
overlay不重新初始化Linux使用的PS DDR；PL时序、路由与功能DRC仍须独立通过。

## CPU-only baseline（旧入口）

先构建三组固件和镜像：

```powershell
python scripts/cpu_baseline/build.py
```

分别运行 RTL 仿真：

```text
vivado -mode batch -source scripts/cpu_baseline/run.tcl -tclargs rv32i
vivado -mode batch -source scripts/cpu_baseline/run.tcl -tclargs rv32im_iterative
vivado -mode batch -source scripts/cpu_baseline/run.tcl -tclargs rv32im_fast
```

每组日志保存到 `results/cpu_baseline/<config>/simulate.log`，testbench 必须报告
`CPU_BASELINE_PASS cases=8 checks=4096`。可直接打开的入口是：

```text
vivado/cpu_baseline_rv32i/cpu_baseline.xpr
vivado/cpu_baseline_rv32im_iterative/cpu_baseline.xpr
vivado/cpu_baseline_rv32im_fast/cpu_baseline.xpr
```

实现一组或全部配置：

```text
vivado -mode batch -source scripts/cpu_baseline/implement.tcl -tclargs rv32i
vivado -mode batch -source scripts/cpu_baseline/implement.tcl -tclargs rv32im_iterative
vivado -mode batch -source scripts/cpu_baseline/implement.tcl -tclargs rv32im_fast
```

资源、时序和 DRC 报告写入 `results/cpu_baseline/`；BIT 写入对应的
`release/cpu_baseline_<config>/`。这些工程只执行 CPU baseline，不包含 PQC HLS。

## ML-KEM-512 官方 RTL 回归

KeyGen 首例和完整 145 条套件使用独立的 CPU/BRAM 仿真工程：

```text
vivado -mode batch -source scripts/mlkem_baseline/run.tcl -tclargs rv32im_fast
vivado -mode batch -source scripts/mlkem512_suite/run.tcl -tclargs rv32im_fast
```

将 `rv32im_fast` 替换为 `rv32i` 或 `rv32im_iterative` 可运行另外两组。完整套件按批次
运行和恢复：

```powershell
python scripts/mlkem512_suite/run.py --help
python scripts/mlkem512_suite/resume.py --help
python scripts/mlkem512_suite/collect_resumed.py --check
```

每组结果位于 `results/official_baseline/mlkem512/`，每组固定 145 条。主机端 512/768/1024
参考回归：

```powershell
python scripts/kat/validate_acvp_json.py
powershell -ExecutionPolicy Bypass -File scripts/kat/run_host_acvp.ps1
```

主机结果位于 `results/official_reference/`。

## 新 HLS BaseMul

本目录的路径较短时可直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File hls/mlkem512_basemul_k2/run_csim.ps1
powershell -ExecutionPolicy Bypass -File hls/mlkem512_basemul_k2/run_hls_short.ps1
```

`run_csim.ps1` 运行 103 个 C 仿真用例；`run_hls_short.ps1` 将源码复制到短路径，调用
Vitis HLS 2024.2 的 `vitis_hls.bat`，并把综合报告和 IP 归档回仓库。也可在目录内执行：

```text
vitis_hls -f run_hls.tcl
```

生成的本地 HLS 工程目录不提交。源文件、TB、配置、Tcl 和导出的 IP 位于
`hls/mlkem512_basemul_k2/`；综合证据位于 `results/accelerator_interface/hls_synthesis/`。

## 独立 MMIO/BRAM 与 Vivado 验证

新 HLS 通过 `rtl/accelerator/mlkem512_basemul_k2_mmio_adapter.sv` 接入双口 BRAM，
MMIO 基址为 `0x50001000`。当前工程先验证独立硬件数据路径，不包含 PicoRV32 或完整 KEM：

```powershell
python scripts/mlkem512_basemul_k2/generate_vectors.py
vivado -mode batch -source scripts/mlkem512_basemul_k2/run.tcl
vivado -mode batch -source scripts/mlkem512_basemul_k2/implement.tcl
```

`run.tcl` 在 `build/basemul_rtl/` 运行仿真，避免覆盖已实现的工程；执行 3 组、768 个系数
的 MMIO RTL 回归，并运行两次 PYNQ-Z2 BIST/时钟复位
测试和一次结果故障注入；`implement.tcl` 生成 Vivado 2024.2 工程、布局布线报告和
`release/mlkem512_basemul_k2/mlkem512_basemul_k2_validation.bit`。缓存、`.runs`、`.sim`
和 `.cache` 目录由 `.gitignore` 排除，入口工程为
`vivado/mlkem512_basemul_k2/basemul.xpr`。

当前独立验证结果位于 `results/accelerator_interface/rtl_sim/` 和
`results/accelerator_interface/vivado_impl/`。RV32IM-fast CPU+PQC 官方 ML-KEM-512
回归已完成，结果位于 `results/accelerator_cpu/kat/`；145 条全部通过，但端到端为
0.9930×，后续优化应先降低批量搬运、轮询和读回开销。不能把独立 BIST 结果称为完整
KEM 性能收益，也不能把该 K=2 核心直接宣称支持 ML-KEM-768/1024。


## ML-KEM-768/1024 CPU-only 可恢复回归

新入口仅接受768/1024，避免覆盖512冻结基线。默认128 KiB RAM、32 KiB栈；同一参数下
所有CPU配置的RAM一致。已有通过结果无需重跑，构建不得与使用同一输入的仿真并发。

```powershell
python scripts/mlkem_suite/build.py --parameter-set 1024
python scripts/mlkem_suite/resume.py --parameter-set 1024 --prepare-only
python scripts/mlkem_suite/resume.py --parameter-set 1024 --config rv32im_fast
python scripts/mlkem_suite/collect.py --parameter-set 1024 --write
python scripts/mlkem_suite/collect.py --parameter-set 768 --check-only
python scripts/mlkem_suite/collect.py --parameter-set 1024 --write
```

resume每批默认8条、最后1条，独立attempt目录，保存成功断点后可恢复；当前批运行中勿再启动。
新建`build/mlkem_suite/STOP`可在批次结束后停调度，删除该标记后恢复。collector要求完整145条、
官方输入/期望、最终PASS和冻结输入哈希；构建成功不算RTL通过。
768首次运行是完整单次145条，证据在`results/official_baseline/mlkem768/rv32im_fast/`。
该次run_inputs是仿真前哈希，run_snapshot为事后归档，用于核对后续修订前的运行脚本；
额外源码快照并非构建前采集。1024新构建保存命令及源码、链接脚本、编译器和libgcc哈希。
