# 构建、仿真与实现

当前仓库的可复现入口分为四类：CPU-only Vivado 工程、ML-KEM 官方软件回归、新 HLS，
以及独立的 BaseMul MMIO/BRAM/PYNQ-Z2 验证工程。旧完整加速器的根级
`run.tcl/project.tcl`、板级烧录脚本和 transfer 工程已经删除。

## 工具版本

- Vivado 2024.2，器件 `xc7z020clg400-1`
- Vitis HLS 2024.2
- Windows PowerShell、Python 3
- RISC-V GCC 工具链（路径通过 `RISCV_TOOLCHAIN_BIN` 或脚本参数配置）

## CPU-only baseline

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
