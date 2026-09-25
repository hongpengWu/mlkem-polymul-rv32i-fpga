# Vivado 2024.2 验证记录

本文件保留初始目录整理完成时的 **RV32I 基线**验证记录，对应提交 `4753221`。下文的“本次”均指该次整理验证，52 项内容一致性及资源/时序数值不代表后续配置的当前状态。阶段 2 的 RV32IM 迭代乘法指令测试、系统回归、实现结果与源码变更说明统一记录于 [BENCHMARKS.md](BENCHMARKS.md)。

## 环境与范围

- 目标器件：PYNQ-Z2，`xc7z020clg400-1`。
- 验证日期：2026-09-22。
- 构建工具：Vivado 2024.2（Build 5239630）、Vitis HLS 2024.2、随附 RISC-V GCC 13.3.0。
- 板级时钟：输入 125 MHz，PL 工作时钟 100 MHz。
- 默认镜像：`firmware/images/transfer_both_unroll4.mem`。
- 加速核：原有 Vitis HLS 2025.2 生成 RTL，未重新生成。
- 整理范围：目录移动、删除非主线文件、构建入口与文档更新；功能源码和保留的测试/初始化文件内容不变。

## 本次检查

| 检查项 | 状态 | 记录 |
|---|---|---|
| 保留源文件内容一致性 | PASS | 52 项 SHA256 与原提交 `601079b` 完全一致，记录于 `source_integrity.csv` |
| Vivado 2024.2 工程创建 | PASS | 完整工程位于 `vivado/project/`，包含 VIO IP 与四个仿真集 |
| 工程迁移与重复生成 | PASS | 仅导出 Git 待提交文件到新目录，直接打开 XPR、生成 VIO 输出后 62 个工程文件均在新根目录内且存在；再次用 Tcl 重建工程并通过核心仿真 |
| 核心仿真 `core` | PASS | 三组算术测试 |
| 协议仿真 `protocol` | PASS | AXI/BRAM 事务与边界用例 |
| 板级仿真 `board` | PASS | 固件、LED=0101 与按钮复位 |
| 板级 VIO 仿真 `vio` | PASS | 三次复位均通过独立 256 系数参考计算、周期和 VIO 连接检查 |
| 四模式固件重编译 | PASS | RV32I/ILP32、RAM 布局及无 M 指令检查通过；四个镜像逐 word 与原镜像相同 |
| 综合、布局布线、bitstream | PASS | BIT/LTX 位于 `release/`；时序满足约束，DRC 无 Error，存在下述 Warning |
| HLS 2024.2 C 仿真 | PASS | 三组测试通过，`CSim done with 0 errors`；只验证 C 算法，不建立 RTL 等价关系 |
| 实体开发板烧录与验收 | 未执行 | 本次整理未配置实体开发板 |

通过标记、复现命令和各测试覆盖范围见 [BUILD.md](BUILD.md)。后续配置的实际结果与失败原因应记录至 [性能与资源数据表](BENCHMARKS.md)，保留本表作为基线；不能把命令成功退出或 bitstream 文件存在单独视为功能正确及满足时序的证明。

## 本次实现结果

| 指标 | 数值 |
|---|---:|
| 工作时钟 | 100 MHz |
| WNS / WHS / WPWS | +1.027 / +0.023 / +2.000 ns |
| Setup / hold / pulse-width 失败端点 | 0 / 0 / 0 |
| 无时钟寄存器 / 未约束内部端点 | 0 / 0 |
| Bus-skew 最差余量（4 条约束全部通过） | +9.158 ns |
| LUT / FF | 3956 / 5053 |
| DSP48E1 | 1 |
| RAMB36 / RAMB18 | 4 / 5（6.5 BRAM36 等效） |
| 系统 Call / 核心 Core | 13952 / 4789 周期 |

周期结果来自 RTL 仿真。Call 范围为本地 RAM 输入就绪至结果读回，不含输入生成和结果检查；Core 与 Poll 重叠，不能额外加到 Call。实体板结果尚未重新验证。

## 报告与保留警告

资源、时序、DRC、bus-skew 报告位于本机 `build/reports/`。四套仿真的 `simulate.log` 位于 `vivado/project/mlkem_pynqz2.sim/` 对应仿真集；HLS 日志位于 `build/hls_csim/logs/hls_run_csim.log`。这些本地运行记录不加入 Git。

本轮没有通过修改源码或约束消除警告。DRC 共 23 个 Warning，涉及单 DSP 的 MREG 流水建议、调试核 LUT/布线检查，以及纯 PL 设计的 `ZPS7-1`（未实例化 PS7）。时序方法检查另提示异步复位 LUT 和 RAM 优化建议。BTN0 和四个 LED 按原有 XDC 设置时序例外。固件链接的 RWX 段警告符合原统一程序/数据 RAM 布局；HLS 编译还报告 AMD `gmp.h` 宏重定义。上述信息保留供后续维护，本次不改变设计实现。

VIO 有 13 个输入端口；生成 LTX 将最后一个两位端口拆为 `done`、`trap`，共 14 个探针条目，与现有读回脚本一致。

## 主机端 FIPS 203/ACVP 参考验证

在 2026-09-23 固定的 ACVP-Server 提交和 `mlkem-native` 参考实现上，结构检查与主机端
回归均通过：

| 向量集 | 用例数 | 结果 |
|---|---:|---|
| ML-KEM-keyGen-FIPS203 | 75 | PASS |
| ML-KEM-encapDecap-FIPS203 | 165 | PASS |
| ML-KEM-encapDecap-FIPS203-tr1 | 195 | PASS |
| 合计 | 435 | PASS |

可复现入口为 `python scripts/kat/validate_acvp_json.py` 和
`scripts/kat/run_host_acvp.ps1`。原始运行日志和元数据保存在
`results/official_reference/`，向量来源和 SHA-256 见
`vectors/official_kat/acvp/SOURCES.md`。该验证只证明主机参考实现与这些 ACVP 结果一致，
尚未证明 PicoRV32 固件、现有多项式加速器或实体 PYNQ-Z2 通过完整 ML-KEM KAT。

## PicoRV32 官方 KeyGen 首例验证（2026-09-24）

新增 freestanding `mlkem-native` 便携 C 固件在真实 PicoRV32/AXI/XPM RAM 的 Vivado 2024.2
RTL 仿真中执行 ML-KEM-512 `keypair_derand(d || z)`。三组统一 64 KiB RAM 和 16 KiB 栈，
原 RTL/HLS 与之前 16 KiB 多项式工程未改。

| 检查 | 结果 | 证据 |
|---|---|---|
| RV32I 官方 tcId=1 | PASS，输入 64 B / 输出 2432 B 逐字节一致 | [日志](../results/official_baseline/keygen512_tc1/rv32i/simulate.log) |
| RV32IM 迭代官方 tcId=1 | PASS，同一输入与 oracle | [日志](../results/official_baseline/keygen512_tc1/rv32im_iterative/simulate.log) |
| RV32IM 快速官方 tcId=1 | PASS，与迭代共用同一固件 | [日志](../results/official_baseline/keygen512_tc1/rv32im_fast/simulate.log) |
| 周期与 M 指令窗口 | PASS，实际 rdcycle 边沿与固件差值一致 | [汇总](../results/official_baseline/keygen512_tc1/summary.json) |
| 固件/fixture/源码追溯 | PASS，来源 SHA、镜像 SHA 与构建清单一致 | [构建清单](../results/official_baseline/keygen512_tc1/build_manifest.json) |
| 错误输出拒绝 | PASS，临时 ek[0] 翻转 1 bit，被准确定位拒绝 | [预期失败日志说明](../results/official_baseline/keygen512_tc1/negative_check/README.md) |
| 新 64 KiB 配置实现、烧录、完整 KEM | 待执行 | 不复用原 16 KiB 资源或 BIT 作为新配置证据 |

`KATP` 只是固件成功返回标记；只有 TB 完成全部输入输出对照并打印
`MLKEM_KEYGEN_PASS` 才认定此例正确。计时排除启动、输入输出调试串流和 TB 检查，
保留默认库内清零；官方种子预置，未测随机熵源。具体数值与边界见 [BENCHMARKS.md](BENCHMARKS.md)。

## PicoRV32 ML-KEM-512 全量验证（2026-09-24）

三组真实 CPU RTL 均通过 145 / 145 条固定版本官方 ACVP 记录，共保留 435 次执行。每组按原始编号覆盖 KeyGen 25、Encaps 50、Decaps 20、含种子展开 Decaps 10、公钥检查 20、私钥检查 20；合法/非法密钥返回值和 15 条隐式拒绝密钥全部与官方预期一致。

| 检查 | 结果 | 证据 |
|---|---|---|
| RV32I / RV32IM 迭代 / 快速 | 各 145 / 145，原始编号完整且唯一 | [逐条结果](../results/official_baseline/mlkem512/cases.csv) |
| 输入 / 输出逐字节对照 | 每组 148,160 / 101,760 B 全部一致 | [汇总](../results/official_baseline/mlkem512/summary.json) |
| 实际 rdcycle、M 指令、栈和地址边界 | PASS；两种 IM 每例指令计数相同，最大观测栈 12,928 B | [统计](../results/official_baseline/mlkem512/summary.md) |
| 断点、批次来源与工程参数 | 94 条旧记录 + 44 批；SHA、实际加载镜像与 fixture、XPR 参数均通过 | [批次证据](../results/official_baseline/mlkem512/batches/) |
| 比较器负向检查 | 翻转 ek[0] 一位后精确拒绝：got=28 expected=29 | [负向检查](../results/official_baseline/mlkem512/negative_check/README.md) |

运行 `python scripts/mlkem512_suite/collect_resumed.py --check` 可复验全部归档证据；`resume.py` 会校验并跳过通过批次。旧前缀没有最终 PASS，不伪造单次全套成功日志或全程总数。CPU/HLS 算法源码未因续跑修改，TB 仅增加批长参数。此结果为公开向量 RTL 回归；快速 CPU 的 512 阶段 profiling 已完成，64 KiB 配置实现、接口接入、768/1024 的 CPU 回归与实板仍待完成。
