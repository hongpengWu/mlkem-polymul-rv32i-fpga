# 项目进度与执行记录

更新时间：2026-09-25。本页汇总已完成工作、当前覆盖范围和下一步；详细数值以
[BENCHMARKS.md](BENCHMARKS.md) 和对应原始日志为准，长期阶段门见
[COMPETITION_ROADMAP.md](COMPETITION_ROADMAP.md)。

## 最新执行状态：独立 BaseMul 硬件验证完成，准备接入快速 CPU

2026-09-25 完成新 K=2 BaseMul 的独立 MMIO/BRAM/BIST 路径：3 组、768 个系数的 RTL
核对及接口异常检查通过，BIST 两次完整运行和结果故障注入通过。Vivado 2024.2 在
100 MHz 下实现通过，WNS/WHS 为 **0.732/0.129 ns**，使用 **8 个 BRAM 原语、12 个 DSP**，
已保存 XPR、bitstream 和报告。当前尚未接 PicoRV32 或官方 KAT，下一步接入未插桩
RV32IM-fast 软件，建立同一官方输入和计时边界的 CPU-only/CPU+PQC 对照。

2026-09-25 新增 RV32IM 快速乘法独立 profiling：**145/145 条记录、19/19 个批次通过**。
各阶段独占周期之和逐例等于 API 总周期，官方输出、返回值、M 指令和内存边界核验通过。
KeyGen / Encaps / 展开私钥 Decaps 的 Keccak 占比分别为 **80.69% / 72.96% / 71.36%**，
多项式算术合计为 **13.08% / 19.13% / 21.38%**；插桩对主要 API 的扰动约 +0.13%–+0.15%。
原基线保持不变。完整表、测量方法与接口任务见 [阶段分析报告](MLKEM512_PROFILE.md)。

主线固定为 RV32IM 快速乘法＋软件与相同 CPU＋PQC 硬件对照；标准库与旧核的
运算域、缩放和缓存向量乘加接口已经审计，新 K=2 BaseMul HLS 及独立 MMIO/BRAM
路径已验证，下一步接通快速 CPU 的完整 KEM。
根据本轮实测，后续同时评估 Keccak 与多项式加速范围；另外两种 CPU 硬件消融后补。

2026-09-24 已完成三组 PicoRV32 CPU 配置的 145 条固定版本官方 ACVP 记录。每组均逐字节核对输入、输出和 API 返回值，并核对实际 `rdcycle` 区间、动态 M 指令计数、栈边界和工程输入哈希；错误输出负向检查也通过。结果是 RTL 仿真证据，不是实板数据或正式 CAVP 认证。

| 配置 | 已通过 / 总项数 | 总算法区间周期 | 全部算法区间 M | 最大观测算法栈 |
|---|---:|---:|---:|---:|
| RV32I | 145 / 145 | 1,400,566,832 | 0 | 12,928 B |
| RV32IM 迭代 | 145 / 145 | 812,132,449 | 3,486,720 | 12,928 B |
| RV32IM 快速 | 145 / 145 | 692,273,249 | 3,486,720 | 12,928 B |

全量结果见 [ML-KEM-512 汇总](../results/official_baseline/mlkem512/summary.md)、[结构化数据](../results/official_baseline/mlkem512/summary.json) 和 [逐条记录](../results/official_baseline/mlkem512/cases.csv)。结果由关机前保存的 94 条记录与 44 个独立批次合并；每条原始 `case_index` 恰好一次，未拼造单次全套 PASS。由于旧前缀没有最终 PASS，summary 中整套启动总周期和整套全程 M 保持不可用；上表只列全部 API 算法区间的真实累加值。

## 1. 已确认的项目方向

**ML-KEM-512 做主要优化和展示，ML-KEM-768/1024 验证正确性与扩展能力。**
纯 CPU 软件 baseline 已在 Vivado 中由真实 PicoRV32＋BRAM RTL 执行固件验证。
旧完整板级加速链已清理；新 HLS 的独立 MMIO/BRAM adapter、BIST 仿真和实现已通过。
下一步接入 RV32IM-fast 并运行官方 KAT，随后完成同配置软件/硬件实现对照，实板仍放到最后。

| 工作范围 | ML-KEM-512 | ML-KEM-768 / 1024 |
|---|---|---|
| NIST 安全类别 | 1，主目标应用的安全等级 | 3 / 5，扩展参数集 |
| 官方公开向量正确性回归 | 三种 CPU 各 145 条已完成 | 主机已通过；三种 CPU 对应测试待做 |
| CPU 基本性能与内存 | 三种 CPU 完整 API 已测；快速乘法全量阶段分析已完成 | 三种 CPU 补齐基本周期、代码、RAM 和栈需求 |
| 加速器优化 | 重点分析阶段耗时、数据搬运、BRAM 和多 PE | 验证共用计算核心和接口的兼容性 |
| 设计空间与资源权衡 | 重点开展，形成主要竞赛结论 | 最终选定架构补充代表性性能和存储结果 |
| 最终应用展示 | 主要展示对象 | 展示其他参数集的功能验证结果；参数切换能力另行验证 |

三参数集每个多项式都为 256 个系数，模数均为 3329；向量维度分别为 2、3、4，
并有采样和压缩参数差异。选择 512 是已确认的优化目标，后续仍需用测得的延迟和
存储开销支撑平台取舍，不预先认定 PYNQ-Z2 无法运行 768/1024。
主线不针对固定 KAT 输入特化；同时支持三个 ML-KEM 参数集也不等于支持多个密码算法。

## 2. 当前完成情况

| 工作项 | 当前状态 | 证据或入口 |
|---|---|---|
| 仓库整理与 Vivado 2024.2 重建入口 | 已完成；保留当前源码、必要 TB/Tcl、CPU-only 与独立加速器 XPR/bitstream | [目录规则](STRUCTURE.md)、[构建说明](BUILD.md) |
| PicoRV32 迭代 M 扩展验证 | 已通过 8 类 M 指令共 4096 项检查；三组 CPU baseline 回归通过 | [CPU baseline 证据](../results/cpu_baseline/) |
| ML-KEM-512 baseline 与阶段分析 | 三组基线离线分析完成；快速乘法 profiling 全部 145 条通过 | [基线解释](MLKEM512_BASELINE_ANALYSIS.md)、[阶段分析](MLKEM512_PROFILE.md) |
| 纯 CPU 多项式软件 baseline | RV32I、RV32IM 迭代、RV32IM 快速均完成 8 组输入检查及周期测量 | [CPU baseline 结果](../results/cpu_baseline/) |
| 旧 16 KiB CPU baseline 实现 | 三组已完成综合、布局布线、资源/时序报告和 bitstream；本轮未做实板复验 | [性能台账](BENCHMARKS.md) |
| 官方向量与参考实现冻结 | 已记录 ACVP 来源、提交、SHA-256 和参考实现版本 | [向量来源](../vectors/official_kat/acvp/SOURCES.md) |
| 电脑主机上的标准参考回归 | 512/768/1024 合计 435 项通过；包含不同操作和检查类型 | [主机结果](../results/official_reference/) |
| PicoRV32 ML-KEM-512 官方全集 | 三种 CPU 各 145 条通过，覆盖六类操作、两类密钥检查的有效/无效结果及隐式拒绝 | [全量汇总](../results/official_baseline/mlkem512/summary.md) |
| 输入、输出和执行真实性检查 | 每组核对 148,160 B 输入和 101,760 B 输出；检查实际 rdcycle、M 指令、栈和异常 | [验证记录](VALIDATION.md) |
| 错误输出拒绝检查 | 临时预期公钥首字节翻转后，被全量 TB 准确拒绝 | [负向检查](../results/official_baseline/mlkem512/negative_check/README.md) |
| 标准软件的完整 CPU baseline | 512 API 与快速 CPU 阶段分析已完成；768/1024 CPU 回归及 64 KiB 实现仍待做 | [M2 路线](COMPETITION_ROADMAP.md#m2picorv32-完整软件-baseline) |
| 标准库接口审计与新 HLS 原型 | C 仿真 103/103、HLS 综合通过；137 cycles 为核心估算，II=1、估算 Fmax 150.83 MHz | [接口契约](MLKEM512_ACCELERATOR_INTERFACE.md)、[新 HLS](../hls/mlkem512_basemul_k2/) |
| 独立 MMIO/BRAM/BIST 与 Vivado 实现 | RTL 3 组、768 个系数及接口检查通过；核心实测 136 cycles；BIST、100 MHz 实现和 bitstream 已完成 | [RTL 证据](../results/accelerator_interface/rtl_sim/)、[实现报告](../results/accelerator_interface/vivado_impl/) |
| PQC 加速器接入标准软件 | 下一步；独立 adapter 已完成，尚未连接 PicoRV32 或参与官方 KAT | [新 HLS 接口](MLKEM512_ACCELERATOR_INTERFACE.md) |
| 新标准软件配置的实现与实板 | 64 KiB ML-KEM-512 工程已完成 RTL 回归；实现待做，实板放到最后 | [512 测量协议](MLKEM512_BENCHMARK_PROTOCOL.md) |

### 当前官方用例覆盖

| 执行环境 | ML-KEM-512 | ML-KEM-768 | ML-KEM-1024 |
|---|---|---|---|
| 电脑主机参考实现 | 145 项所选记录通过 | 145 项所选记录通过 | 145 项所选记录通过 |
| PicoRV32 RV32I RTL | 145 项所选记录通过 | 待测 | 待测 |
| PicoRV32 RV32IM 迭代 RTL | 145 项所选记录通过 | 待测 | 待测 |
| PicoRV32 RV32IM 快速 RTL | 145 项所选记录通过 | 待测 | 待测 |
| CPU＋PQC 加速器标准软件 | 待接入与验证 | 待接入与验证 | 待接入与验证 |
| 本项目标准软件实板回归 | 最后执行 | 最后执行 | 最后执行 |

主机的 435 项是 `75 + 165 + 195`，来自固定版本 FIPS203 keyGen、FIPS203 encapDecap
和 FIPS203-tr1 encapDecap 数据集。PicoRV32 本次的 435 次执行则是同一 512 集合在三种 CPU
上各执行 145 项；两者口径不同，不能据此称 PicoRV32 已覆盖三个参数集。
每参数集为 `25 + 55 + 65 = 145` 项记录，其中包含密钥检查，不能统称 145 次完整 KEM。
后续按数据集/修订、操作、参数集、tgId、tcId 登记覆盖，保留检查型用例与运算型用例的区别。

### 历史 KeyGen 首例测量快照

| CPU 配置 | KeyGen 周期 | 按 100 MHz 换算 | 相对 RV32I | 动态 MUL |
|---|---:|---:|---:|---:|
| RV32I | 8,995,082 | 89.95082 ms | 1.0000× | 0 |
| RV32IM 迭代 | 5,812,531 | 58.12531 ms | 1.5475× | 18,176 |
| RV32IM 快速 | 5,194,547 | 51.94547 ms | 1.7316× | 18,176 |

这三个结果各来自一个用例的一次确定性 KeyGen 调用，包含库内默认清零，排除启动、
种子准备、熵源采集、调试传输和 TB 检查；空计时区间 4 周期不扣除。
该历史单例表不表示完整 KEM 耗时或 PQC 加速器加速比；当前通用驱动的完整用例分布
见上方 512 全量汇总，其操作分派和外围指令与旧首例驱动不同。

历史首例三组统一 64 KiB RAM、16 KiB 栈预留，观测栈使用 9,328 B，RV32I/RV32IM
有效镜像分别为 19,424 / 18,848 B。当前全量驱动的对应镜像为 27,808 / 26,272 B，
全部 145 条的最大观测算法栈为 12,928 B，仍保留同样的 RAM 和栈容量；观测值不是最坏输入上界。
原 16 KiB 多项式工程的资源与 bitstream 不能作为新配置的实现证据；
100 MHz 是仿真时钟换算，新配置的布局布线频率和资源仍待测。

## 3. 接下来的执行顺序

| 顺序 | 任务 | 完成标志 | 当前状态 |
|---|---|---|---|
| 1 | ML-KEM-512 Encaps、Decaps 各跑通官方首例 | 三种 CPU 核对相同官方输入/输出，形成独立日志 | 已完成 |
| 2 | 补齐 ML-KEM-512 所选官方集 | KeyGen、Encaps、Decaps、key-check 和隐式拒绝记录通过 | 已完成，三组各 145 / 145 |
| 3 | ML-KEM-512 快速 CPU 阶段分析 | 145 条阶段和 API 周期完整对应，量化插桩扰动 | 已完成 |
| 4 | 标准库与加速核接口契约、阶段 oracle | 对齐 NTT 域、缩放、系数范围/顺序、缓存和向量累加 | 接口审计完成；新 BaseMul C 仿真通过 |
| 4a | 独立 HLS＋BRAM＋MMIO 验证 | RTL、BIST、布局布线与匹配 XPR/bitstream | 已完成；尚未接 CPU |
| 5 | 快速 CPU＋多项式加速器主线接通 | 完整 512 官方回归及未插桩 API 软件/硬件对照，计入搬运/等待 | 待执行 |
| 6 | 主线 64 KiB 配置 Vivado 实现 | 同条件软件/硬件资源、时序与 bitstream；不沿用旧 16 KiB 报告 | 待执行 |
| 7 | Keccak 加速及与多项式协同评估 | 软件、仅多项式、仅 Keccak、两者协同的周期和资源可比 | 待执行 |
| 8 | 512 存储/计算优化 | 搬运分解、BRAM、适用的多 PE 和流水化，有资源/性能前后数据 | 待执行 |
| 9 | 其他 CPU 消融及 768/1024 扩展 | 补齐官方回归、基本周期/内存、最终架构验证及适用实现结果 | 待执行 |
| 10 | 完成上板前验收 | 系统回归、适用异常/故障检查、实现时序与匹配烧录产物准备完毕 | 待执行 |
| 11 | 最后进行 PYNQ-Z2 实板和演示 | 功能、周期读回及适用板级功耗数据，与仿真/实现证据对应 | 最后阶段 |

无需让 768/1024 重复 512 的每一轮架构扫参；保留完整所选向量回归、基本测量和最终架构验证。
若不同参数集使用不同内存容量，报告中需明确，不能把不同配置的结果当作只改变算法参数的对照。

## 4. 对外表述与证据边界

当前可表述为：

> 固定版本参考实现在主机上通过 435 项 NIST ACVP 官方公开向量回归；三种 PicoRV32
> 配置在 RTL 仿真中均通过全部 145 条固定版本 ML-KEM-512 官方记录，覆盖 KeyGen、Encaps、
> 两种 Decaps 形式及密钥检查。快速乘法 CPU 的 512 全量阶段分析和新 BaseMul 的独立
> MMIO/BRAM/BIST、Vivado 2024.2 实现已完成；PicoRV32 硬件接入、768/1024 CPU 回归、
> 64 KiB 系统实现及标准软件的硬件加速对照仍待完成。

全部对应回归完成后，可以描述所覆盖版本、参数集、操作和用例的结果一致性。
公开向量离线回归不等于正式 CAVP 算法验证，也不等于 FIPS 140-3 / CMVP 密码模块认证；
测试通过不能单独证明所有合法输入下完全正确、恒定时间或侧信道安全。

## 5. 文档维护与本次记录

- 当前进度和下一步：本文件。
- 目标、范围与长期验收门：[COMPETITION_ROADMAP.md](COMPETITION_ROADMAP.md)。
- 性能/资源详细台账：[BENCHMARKS.md](BENCHMARKS.md)；原始证据在 `results/`。
- 命令与操作：[BUILD.md](BUILD.md)；验证范围：[VALIDATION.md](VALIDATION.md)。

以下记录保留各阶段完成时的范围；提交状态以 Git 为准。

2026-09-24 决策：确定“512 重点优化、768/1024 正确性与扩展验证”，实板放在上板前工作之后。
本次保留关机前 94 条记录，完成其余 341 次执行的 44 个批次，并经严格汇总确认三组各 145 条。
逐例日志、映射、输入哈希和便携工程证据已保存；未进行 64 KiB 实现、加速器集成或实板测试。
本轮未提交 Git，提交状态以工作区为准。

2026-09-25：独立插桩镜像完成 19 批、145 条 RTL 回归；正式软件基线、第三方库、CPU/HLS
原文件保持不变。阶段 CSV、完整统计、构建与批次哈希已归档，新增可断点续跑入口。
未进行新综合/实现、硬件接入或实板操作，修改仍未提交。

2026-09-25：完成标准库/加速器接口审计；旧 HLS 明确标记为 legacy baseline。新建
`hls/mlkem512_basemul_k2/`，以独立 testbench 覆盖零值、规范值、signed lazy 边界和
100 组确定性随机输入，C 仿真 103/103 通过；Vitis HLS 2024.2 短路径综合通过，得到
137 cycles、II=1 和估算 Fmax 150.83 MHz；尚未进行完整 Vivado 工程接入、AXI 适配、CPU
接入或官方 KAT 硬件回归。

2026-09-25 后续：独立 MMIO/BRAM/BIST 验证与 Vivado 实现完成，保存
`vivado/mlkem512_basemul_k2/basemul.xpr`、`release/mlkem512_basemul_k2/` 和
`results/accelerator_interface/` 中的证据。现有 CPU baseline 保持不变；下一步接入
RV32IM-fast，以官方 ML-KEM-512 KAT 验证完整 API 并计入搬运、等待和读回成本。
