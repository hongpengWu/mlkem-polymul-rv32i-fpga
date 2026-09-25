# 构建、仿真与实现

当前仓库的可复现入口分为三类：CPU-only Vivado 工程、ML-KEM 官方软件回归和新 HLS。
旧完整加速器的根级 `run.tcl/project.tcl`、板级烧录脚本和 transfer 工程已经删除。

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

## 后续硬件集成边界

新 HLS 是 `ap_ctrl_hs + ap_memory` 接口，尚无 AXI wrapper、CPU 地址映射或完整 Vivado
顶层。后续必须新建 adapter，先做阶段向量 oracle，再做少量官方记录的 CPU+PL 仿真，最后
才进行 64 KiB 实现和实体板烧录。旧的板级脚本、旧 bitstream 和旧 XPR 不再作为入口。
