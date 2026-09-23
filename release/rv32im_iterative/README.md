# PYNQ-Z2 RV32IM 迭代乘法烧录文件

本目录保存 2026-09-22 使用 Vivado 2024.2（Build 5239630）生成的 RV32IM 迭代乘法配置产物，目标为 `xc7z020clg400-1`，工作时钟 100 MHz，保留 BRAM wrapper、4 KiB 固件 RAM 和只读 VIO。

- `mlkem_pynqz2.bit`：CPU 参数为 `ENABLE_MUL=1`、`ENABLE_FAST_MUL=0`、`ENABLE_DIV=1`。
- `mlkem_pynqz2.ltx`：与上述 BIT 匹配的调试探针配置。
- `SHA256SUMS`：BIT 和 LTX 的 SHA-256。

固件仍为 `firmware/images/transfer_both_unroll4.mem`，已初始化在程序 RAM 中，不需额外下载 ELF。该 RV32I 镜像不含 M 指令，用于验证原有加速器传输、自检和计时行为的兼容性；M 指令由独立 CPU 仿真覆盖，当前产物不是软件 NTT 性能基准。

构建已通过 4096 项 M 指令检查、原有 `core`、`protocol`、`board`、`vio` 四组回归，以及综合、布局布线和 bitstream 生成。测量数据、时序与 DRC 范围见 [BENCHMARKS.md](../../docs/BENCHMARKS.md)，原始证据见 [results/rv32im_iterative](../../results/rv32im_iterative/)。本轮按要求未烧录或验收实体开发板。

后续需要烧录时，在 JTAG Hardware Manager 中同时选择本目录的 BIT/LTX。`scripts/program_board.tcl` 仍默认加载 `release/` 中的原始 RV32I 产物，不会自动选择本目录。这是易失性的 PL 配置；没有 BOOT.BIN 或 PS 设计。自检成功时 `LED[3:0]=0101`，BTN0 可复位重跑。

从仓库根目录重新构建：

```text
vivado -mode batch -source scripts/run.tcl -tclargs implement firmware/images rv32im_iterative
```

```powershell
./scripts/update_release_checksums.ps1 -CpuConfig rv32im_iterative
./scripts/collect_rv32im_measurements.ps1
```

完整工程为 [mlkem_pynqz2.xpr](../../vivado/project_rv32im_iterative/mlkem_pynqz2.xpr)。替换产物时应同时更新 BIT、LTX、校验文件和测量证据，汇总实际结果后再更新数据表。
