# 整理与迁移验证记录

日期：2026-09-21。工具：AMD Vivado/Vitis 2025.2，本机 AMD 随附 RISC-V GCC。

## 整理范围

- 原工程不移动、不删除、不改写；新目录是独立副本。
- 默认入口改为实际使用的 BRAM wrapper；旧寄存器 wrapper 及其对照 testbench 隔离到 `experiments/register_wrapper/`。
- 从历史 HLS 源码补齐主文件 include 的 `mlkem_poly_mul256_v39e_unified_stream_support.cpp`，保持内容不变。
- HLS 数学实现、RTL、固件算法和断言预期值均未为了迁移而修改。
- 新增相对路径建工程脚本和 HLS 配置；固件编译器路径改为参数，VIO 采样目录改为 `build/hardware/`。
- 不复制旧缓存、旧 Vivado 工程树、历史 bitstream、论文 PDF、周报、PPT、教授往来材料。
- 保留精选历史证据和本次迁移日志。对证据副本的路径和主机名作明确脱敏，记录前后 SHA256；不改测量结果。

## 已实际执行

| 检查 | 本次结果 | 证据 |
|---|---|---|
| 四模式固件重新编译 | PASS，RV32I / ILP32 / -O2；静态 RAM 检查及无 M 指令检查通过 | `evidence/migration/firmware_build.csv`；本机 `firmware/build/*.dump`、`*.map`、`*.size.txt` |
| 重新编译与归档镜像比较 | 四个 `.mem` 的逐 word 内容全部一致 | baseline 310、write 335、read 346、both 370 words |
| 带 VIO 完整系统仿真 | PASS，使用本次重新编译的 mode-3 固件，三次复位均通过独立 256 系数 oracle 和计数检查 | `evidence/migration/vio_simulate.log` |
| BRAM wrapper 协议仿真 | PASS，16 种字节掩码、分离 AW/W、背压、并发通道、忙时访问、重复执行、复位及环边界 | `evidence/migration/protocol_simulate.log` |
| 不带 VIO 的板级 RTL 仿真 | PASS，归档 mode-3 固件，LED=0101，按钮复位重启 | `evidence/migration/board_simulate.log` |
| HLS C 仿真 | PASS，三种输入均通过独立负循环卷积与输出规范区间检查 | `evidence/migration/hls_csim.log` |
| Vivado 工程源码依赖检查 | 三个工程均通过；脚本拒绝新目录外的工程源码/IP 文件 | `scripts/run.tcl`；本机对应 `mlkem.xpr` |

Vivado 自带器件库、UNISIM、VIO 和 Vitis 头文件仍是必要的工具依赖，不属于应复制到仓库的工程源码。

### 本次复核的系统计数

| 指标 | 周期 |
|---|---:|
| Write | 5873 |
| Start | 19 |
| Poll | 4827 |
| Read | 3233 |
| Call | 13952 |
| Core（与 Poll 重叠，不能另加到 Call） | 4789 |
| Poll 次数 | 185 |
| 连续 rdcycle 差值 | 4 |

`5873 + 19 + 4827 + 3233 = 13952`。计时范围是已有本地 RAM 输入到结果读回本地 RAM，不包括生成输入和检查输出。

### 四模式固件大小

| 模式 | Binary bytes | .text bytes | 静态段末地址 | 到 0x0ff0 的栈间隙 bytes |
|---|---:|---:|---|---:|
| baseline | 1240 | 728 | 0x08d8 | 1816 |
| write unroll x4 | 1340 | 828 | 0x093c | 1716 |
| read unroll x4 | 1384 | 872 | 0x0968 | 1672 |
| both unroll x4 | 1480 | 968 | 0x09c8 | 1576 |

这里验证的是静态布局和保留间隙，不是最大动态栈占用证明。

## 遇到的失败与警告

第一次 HLS C 仿真未进入算法执行，GNU Make 报 `/dev/null:1: missing separator`。本机 D 盘的 `dev/null` 是已有普通文件，内容不是 Makefile。保持该文件不变，在 C 盘新建临时构建目录、继续引用候选目录的同一份源码和配置后，C 仿真通过。第一次失败日志也保存为 `evidence/migration/hls_csim_first_attempt.log`，不能将其隐藏或当作功能失败。复现方法见 BUILD.md。

HLS 编译有来自 AMD 头文件的 `__GMP_LIBGMP_DLL` 重定义警告；最终为 `CSim done with 0 errors`。固件链接有 RWX LOAD 段警告，源于裸机统一程序/数据 RAM 的链接布局；编译成功。此处没有通过屏蔽警告或改测试预期来得到 PASS。

## 在本机直接打开

推荐使用第一个工程。在 Vivado 的 Open Project 中选择：

```text
build/vio_1789989635_50392/mlkem.xpr
build/protocol_1789989767_50084/mlkem.xpr
build/board_1789990031_26528/mlkem.xpr
```

以上均相对于新项目根目录。这些 `.xpr` 是本次真实生成的本地产物；发布候选文件不包含 build 缓存，其他电脑运行 `scripts/run.tcl` 重建即可。迁移项目路径后也应重建，不继续依赖生成工程内部保存的旧绝对路径。

## 尚未验证或不属于本轮

- 没有在新目录重跑 HLS synthesis、C/RTL co-simulation，也未证明重新生成 RTL 与所保留 RTL 在周期、资源上逐项一致。
- 没有从新目录重跑 FPGA implementation、生成新 bitstream 或再次上板。RESULTS.md 的资源、时序和实板值仍来自标明的历史证据。
- `implement` 是提供的显式后续入口，不表示本轮已执行或已验证它的整个后端流程。
- 保留的所有旧实验没有逐一重跑，尤其软件 compute audit 的 PC 地址不能直接用于任意重编译的固件。
- 没有进行安全认证、功耗测试、完整 ML-KEM 测试或抗侧信道验证。
- 没有 GitHub 上传，没有选择许可证；第三方和机构公开权限仍需确认。

## 文件追溯

`SOURCE_MANIFEST.csv` 记录导入时的哈希；`evidence/REDACTION_MANIFEST.csv` 记录证据副本脱敏前后的哈希；`FINAL_MANIFEST.csv` 记录整理后的候选文件。最终清单不包含自身、`build/`、`firmware/build/`、本机日志缓存或临时 HLS 工程。

导入文件哈希复核显示：所有导入的 HLS/RTL、固件、测试、约束和架构图保持原内容。预期差异仅为两个路径调整后的脚本和八份脱敏历史证据。候选源码/文档/证据扫描未发现旧工程绝对路径、用户目录路径或所检查的常见 GitHub token / 私钥头标记；这不替代完整的公开发布审查。
