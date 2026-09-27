# 项目进度与执行记录

更新时间：2026-09-27。本页汇总已完成工作、当前覆盖范围和下一步；详细数值以
[BENCHMARKS.md](BENCHMARKS.md) 和对应原始日志为准，长期阶段门见
[COMPETITION_ROADMAP.md](COMPETITION_ROADMAP.md)。

## 最新执行状态：K=4官方RTL通过；系统资源足够，100 MHz时序待优化

2026-09-27 决策：**ML-KEM-1024（K=4）为优化与展示主线，K=2 冻结为历史对照，
K=3 在主线完成后验证扩展。** 主加速器优先评估 Keccak/FIPS 202 主导工作量候选，
不受旧 BaseMul 范围约束。先按报告优化且保持逐位一致的 HLS，再完成打包/批量接口、
CPU 集成和 K=4 官方 RTL KAT，随后给出同 CPU、同 RAM 的未插桩端到端对照与系统
资源/时序，实板最后进行。K=2 的 Keccak 71%–81% 占比仅属于 K=2；K=4 占比尚未测量。

`hls/mlkem1024_keccak/` 已实现 SHAKE128/256、SHA3-256/512，32-bit BRAM 输入/输出
容量为 2048/4096 B，上下文为 26 个 `uint64`，支持 HASH/SQUEEZE/CLEAR。
io0、io1 均通过 C 仿真与 Verilog COSIM 的 109 笔本地 `hashlib` 差分事务；这不是
ML-KEM 官方 KAT。优化版全 testbench 实测 **75,280 cycles**，基线 **1,314,553 cycles**。
所选 `opt02` 版 HLS 估算 LUT/FF/BRAM18K/DSP 为 **15,244/15,385/2/0**，时钟 **8.895 ns**；
基线为 **14,612/17,008/2/0**、**8.622 ns**。独立 IP OOC 布局布线已完成：100 MHz、WNS/WHS +0.279/+0.098 ns，
16,885 LUT、15,320 FF；外部存储和 CPU 未计入，系统时序待测。`opt02` 相比 `opt01` 只修正长非对齐续读的 LOOP_TRIPCOUNT 上界，
周期/资源不变；物理证据来自 `opt01`，RTL 对比与归档说明见
[K=4 HLS 说明](../hls/mlkem1024_keccak/README.md) 与
[HLS 结果汇总](../results/hls/mlkem1024_keccak/summary.md)。

自动续跑 `pqc-kat` 已按用户要求删除，不再周期性发送指令。

### K4 调用分析与 CPU 接口闭环（2026-09-27）

主机端145条官方K4记录全部匹配，计得8,683次Keccak置换；映射为3,120个HASH和68个SQUEEZE，
输入最多1600B、单命令输出最多504B，现有HLS容量足够。这是调用统计，不是Pico阶段周期。
独立RV32IM-fast＋Keccak系统已通过10次RTL调用、216个结果字，真实HLS启动/完成均为10次。
覆盖四种模式、上下文交错、续取、CLEAR和两类错误返回；固件4888B，RAM/栈128/32KiB。
CPU调用周期合计72,287，硬件busy合计4,070，完整TB326,618；不作为完整KEM或加速比。

标准库FIPS202适配及官方加速RTL **145/145** 已完成，19批全部最终PASS且无重复/缺失。
同RV32IM-fast、128 KiB RAM / 32 KiB栈，API周期合计从 **1,699,294,360** 降至
**446,853,509**，所选测试集总周期比 **3.8028×**，计入打包、搬运、等待、读回及CPU清零。
KeyGen / Encaps / Decaps分别 **4.203× / 3.636× / 3.602×**；含私钥重建的Decaps为3.827×。
3,188次实际HLS启动/完成与预期一致（3,120 HASH＋68 SQUEEZE）；最大观测栈24,384 B。
19批运行时长合计7,056.986 s（约1小时58分，含编译/展开），没有重跑CPU基线。
证据见[加速官方KAT汇总](../results/keccak_cpu/kat/summary.md)。完整系统OOC资源检查已完成，LUT19,084、FF16,970、BRAM34.5、DSP4；100 MHz内部setup −1.367 ns，实板待验证。
详见[接口与移植断点](MLKEM1024_KECCAK_CPU_INTERFACE.md)、
[调用统计](../results/keccak_cpu/call_profile/README.md)、[CPU闭环证据](../results/keccak_cpu/smoke/README.md)。

### 已完成的 CPU 基线与 K=2 历史证据

2026-09-26：ML-KEM-768 和 ML-KEM-1024 的 RV32IM-fast CPU-only 官方记录均已逐字节通过
145/145。算法区间分别为 **1,112,525,793** 和 **1,699,294,360 cycles**，最大观测栈分别为
**18,432 B** 和 **24,464 B**；两组使用 **128 KiB RAM / 32 KiB 栈**，512 原基线仍为
64/16 KiB。K=2（ML-KEM-512）CPU+PQC 加速链路也已通过 145/145，端到端为 0.9930×。
K=4标准库CPU+Keccak已145/145官方RTL通过；系统OOC已完成但100 MHz时序待收敛，K=3硬件扩展后置。
证据见 [768 汇总](../results/official_baseline/mlkem768/rv32im_fast/summary.md)、
[1024 汇总](../results/official_baseline/mlkem1024/rv32im_fast/summary.md) 和
[自动续跑记录](ACCEL_KAT_AUTORUN.md)。

RV32IM-fast 已通过新总线桥执行 MMIO C 驱动，3 组输入的 768 个系数全部核对通过。
调用周期均为 48,632，包含搬入、启动、等待及读回；核心为 136 周期。标准库 native hook
及完整官方套件加速固件已编译链接通过，ML-KEM-512 官方 KAT 已完成 145/145，CPU-only
baseline 保持不变。当前端到端 CPU+PQC 为 0.9930×，说明功能闭环已建立但搬运/轮询开销
仍高于核心节省。详见 [CPU 接口验证](MLKEM512_CPU_ACCEL_SMOKE.md) 和
[加速 KAT 汇总](../results/accelerator_cpu/kat/summary.md)。以下独立实现数据不代表新 CPU
集成系统资源。

2026-09-25 完成新 K=2 BaseMul 的独立 MMIO/BRAM/BIST 路径：3 组、768 个系数的 RTL
核对及接口异常检查通过，BIST 两次完整运行和结果故障注入通过。Vivado 2024.2 在
100 MHz 下实现通过，WNS/WHS 为 **0.732/0.129 ns**，使用 **8 个 BRAM 原语、12 个 DSP**，
已保存 XPR、bitstream 和报告。CPU 最小闭环及标准库官方 KAT 也已通过；145 条记录的
CPU-only/CPU+PQC 对照显示端到端为 0.9930×。该 K=2 路径现冻结保存，作为接口开销的历史证据。

2026-09-25 新增 RV32IM 快速乘法独立 profiling：**145/145 条记录、19/19 个批次通过**。
各阶段独占周期之和逐例等于 API 总周期，官方输出、返回值、M 指令和内存边界核验通过。
KeyGen / Encaps / 展开私钥 Decaps 的 Keccak 占比分别为 **80.69% / 72.96% / 71.36%**，
多项式算术合计为 **13.08% / 19.13% / 21.38%**；插桩对主要 API 的扰动约 +0.13%–+0.15%。
原基线保持不变。完整表、测量方法与接口任务见 [阶段分析报告](MLKEM512_PROFILE.md)。

K=2 标准库与旧核的运算域、缩放和缓存向量乘加接口已经审计，BaseMul HLS 及独立
MMIO/BRAM 路径已验证。这些结果说明核心周期改善不能替代端到端收益；K=4 的加速
范围和结构仍须由自己的报告、调用负载及系统测量决定，其他 CPU 消融后补。

2026-09-24 已完成三组 PicoRV32 CPU 配置的 145 条固定版本官方 ACVP 记录。每组均逐字节核对输入、输出和 API 返回值，并核对实际 `rdcycle` 区间、动态 M 指令计数、栈边界和工程输入哈希；错误输出负向检查也通过。结果是 RTL 仿真证据，不是实板数据或正式 CAVP 认证。

| 配置 | 已通过 / 总项数 | 总算法区间周期 | 全部算法区间 M | 最大观测算法栈 |
|---|---:|---:|---:|---:|
| RV32I | 145 / 145 | 1,400,566,832 | 0 | 12,928 B |
| RV32IM 迭代 | 145 / 145 | 812,132,449 | 3,486,720 | 12,928 B |
| RV32IM 快速 | 145 / 145 | 692,273,249 | 3,486,720 | 12,928 B |

全量结果见 [ML-KEM-512 汇总](../results/official_baseline/mlkem512/summary.md)、[结构化数据](../results/official_baseline/mlkem512/summary.json) 和 [逐条记录](../results/official_baseline/mlkem512/cases.csv)。结果由关机前保存的 94 条记录与 44 个独立批次合并；每条原始 `case_index` 恰好一次，未拼造单次全套 PASS。由于旧前缀没有最终 PASS，summary 中整套启动总周期和整套全程 M 保持不可用；上表只列全部 API 算法区间的真实累加值。

## 1. 已确认的项目方向

**ML-KEM-1024 是当前主线；ML-KEM-512 保留历史对照；ML-KEM-768 后置扩展。**
纯 CPU 软件 baseline 已由真实 PicoRV32＋BRAM RTL 执行固件验证。K=2 加速通过记录
和独立实现均保留，但不能用于证明 K=4 CPU+加速器系统的正确性、性能或资源。

| 工作范围 | ML-KEM-1024（K=4） | ML-KEM-512（K=2） | ML-KEM-768（K=3） |
|---|---|---|---|
| NIST 安全类别与定位 | 5，优化与展示主线 | 1，冻结历史对照 | 3，后置扩展 |
| 官方公开向量正确性回归 | fast CPU与CPU+Keccak各145/145 | 三种 CPU 各 145/145；加速 145/145 | fast CPU 145/145；加速扩展待测 |
| CPU 基本性能与内存 | 128 KiB RAM / 32 KiB 栈；阶段占比待测 | 64 KiB RAM / 16 KiB 栈；已完成阶段分析 | 128 KiB RAM / 32 KiB 栈；保留已测数据 |
| 加速器优化 | 报告驱动 Keccak/FIPS 202 HLS，随后批量接口与集成 | 保留 BaseMul 0.9930× 对照，不继续主线扫参 | 在 K=4 最终架构上验证兼容性 |
| 设计空间与资源权衡 | 逐位等价、Core/Call/API 周期和系统资源/时序 | 历史证据 | 后置代表性结果 |
| 最终应用展示 | 主要展示对象，实板最后 | 历史对照 | 扩展功能证据 |

三参数集每个多项式都为 256 个系数，模数均为 3329；向量维度分别为 2、3、4，
并有采样和压缩参数差异。K=4 的平台取舍须由测得的延迟、存储和实现资源支撑；
不得把 K=2 阶段占比或独立加速器实现数字直接套到 K=4。
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
| 标准软件的完整 CPU baseline | 512 API/阶段分析和768/1024 RV32IM-fast CPU全集完成；K4阶段占比、其他CPU消融待测 | [M2 路线](COMPETITION_ROADMAP.md#m2picorv32-完整软件-baseline) |
| K=2 标准库接口审计与历史 HLS 原型 | C 仿真 103/103、HLS 综合通过；137 cycles 为核心估算，II=1、估算 Fmax 150.83 MHz | [接口契约](MLKEM512_ACCELERATOR_INTERFACE.md)、[K=2 HLS](../hls/mlkem512_basemul_k2/) |
| 独立 MMIO/BRAM/BIST 与 Vivado 实现 | RTL 3 组、768 个系数及接口检查通过；核心实测 136 cycles；BIST、100 MHz 实现和 bitstream 已完成 | [RTL 证据](../results/accelerator_interface/rtl_sim/)、[实现报告](../results/accelerator_interface/vivado_impl/) |
| K=2 PQC 加速器接入标准软件 | 冻结历史对照；CPU+驱动及官方 KAT 145/145 通过，端到端 0.9930× | [CPU 接口验证](MLKEM512_CPU_ACCEL_SMOKE.md)、[KAT 汇总](../results/accelerator_cpu/kat/summary.md) |
| K=4 Keccak/FIPS 202 HLS | io0/io1 的 C 与 Verilog COSIM 均通过 109 笔本地差分事务；独立 IP OOC 实现已完成，系统OOC已测、100 MHz时序待收敛 | [HLS 说明](../hls/mlkem1024_keccak/README.md)、[结果汇总](../results/hls/mlkem1024_keccak/summary.md) |
| K=4 CPU+加速器系统 | 组件10项、标准库官方145/145通过，端到端3.803×；系统资源足够，100 MHz setup待优化；实板待做 | [当前路线](COMPETITION_ROADMAP.md) |

### 当前官方用例覆盖

| 执行环境 | ML-KEM-512 | ML-KEM-768 | ML-KEM-1024 |
|---|---|---|---|
| 电脑主机参考实现 | 145 项所选记录通过 | 145 项所选记录通过 | 145 项所选记录通过 |
| PicoRV32 RV32I RTL | 145 项所选记录通过 | 待测 | 待测 |
| PicoRV32 RV32IM 迭代 RTL | 145 项所选记录通过 | 待测 | 待测 |
| PicoRV32 RV32IM 快速 RTL | 145 项所选记录通过 | 145 项通过，128 KiB RAM | 145 项通过，128 KiB RAM |
| CPU＋PQC 加速器标准软件 | 145 项 RTL 仿真通过；端到端 0.9930×，冻结历史对照 | 后置扩展 | 145项RTL通过；同配置API总周期比3.803× |
| 本项目标准软件实板回归 | 最后执行 | 最后执行 | 最后执行 |

主机的 435 项是 `75 + 165 + 195`，来自固定版本 FIPS203 keyGen、FIPS203 encapDecap
和 FIPS203-tr1 encapDecap 数据集。历史 PicoRV32 的 435 次执行是同一512集合在三种CPU上各145项；
另有768/1024 fast CPU各145项，这是CPU-only覆盖；K4加速系统另有独立145项RTL证据，K3加速扩展待测。
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
| 1 | 保存 K=2 历史对照和 K3/K4 CPU 基线 | 原始日志、配置、哈希及内存差异可追溯 | 已完成 |
| 2 | K=4 报告驱动的精确 HLS 优化 | 保持 FIPS 202 逐位结果；C/COSIM、周期、资源和时序报告完整 | io0/io1 局部差分通过；独立 IP OOC 实现已完成，系统OOC已测、100 MHz时序待收敛 |
| 3 | K=4 打包接口与 CPU 集成 | 明确上下文、搬运、启动、等待和读回契约 | 10次RTL组件调用通过，标准库适配完成 |
| 4 | K=4 CPU+加速器官方 RTL KAT | 所选官方 145 条逐字节通过，真实硬件调用证据完整 | 145/145全量通过，19批最终PASS |
| 5 | K=4 未插桩端到端公平对照 | 同 RV32IM-fast、128 KiB RAM / 32 KiB 栈，完整 API 周期含接口成本；阶段占比独立测量 | 全量端到端3.803×已完成；K4阶段占比独立待测 |
| 6 | K=4 系统资源/时序与设计选择 | 同约束软件/硬件综合和布局布线，记录 LUT/FF/BRAM/DSP/WNS；独立 HLS 估算不替代系统结果 | 两组OOC已完成；加速组setup −1.367 ns，优先优化总线译码到RAM地址链 |
| 7 | K=3 扩展和其他 CPU 消融 | 在选定架构上补齐对应官方回归、基本性能和内存数据 | 后置 |
| 8 | 完成上板前验收 | 系统回归、适用异常/故障检查、实现时序与匹配烧录产物准备完毕 | 待执行 |
| 9 | 最后进行 PYNQ-Z2 实板和演示 | 功能、周期读回及适用板级功耗数据，与仿真/实现证据对应 | 最后阶段 |

K=2 不再进入主线优化队列；K=3 无需重复 K=4 的每一轮扫参，但扩展必须有独立硬件证据。
若不同参数集使用不同内存容量，报告中需明确，不能把不同配置的结果当作只改变算法参数的对照。

## 4. 对外表述与证据边界

当前可表述为：

> 固定版本参考实现在主机上通过 435 项 NIST ACVP 官方公开向量回归；三种 PicoRV32
> 配置在 RTL 仿真中均通过全部 145 条固定版本 ML-KEM-512 官方记录。ML-KEM-768/1024
> 的 RV32IM-fast CPU-only 官方记录也分别通过 145/145；K=2 的 BaseMul 独立
> MMIO/BRAM/BIST、Vivado 2024.2 实现及 CPU+PQC 全流程已完成并冻结。当前主线是
> K=4 Keccak/FIPS 202：局部 HLS 的 C/Verilog COSIM 差分通过，独立 IP OOC 实现已完成，系统OOC已测、100 MHz时序待收敛；
> CPU组件接口10项及完整标准库145条官方RTL记录已通过，同配置测试集API总周期比3.803×；
> 完整系统OOC资源足够，但100 MHz内部setup未闭合（−1.367 ns），实板与K=3后置。

全部对应回归完成后，可以描述所覆盖版本、参数集、操作和用例的结果一致性。
公开向量离线回归不等于正式 CAVP 算法验证，也不等于 FIPS 140-3 / CMVP 密码模块认证；
测试通过不能单独证明所有合法输入下完全正确、恒定时间或侧信道安全。

## 5. 文档维护与本次记录

- 当前进度和下一步：本文件。
- 目标、范围与长期验收门：[COMPETITION_ROADMAP.md](COMPETITION_ROADMAP.md)。
- 性能/资源详细台账：[BENCHMARKS.md](BENCHMARKS.md)；原始证据在 `results/`。
- 命令与操作：[BUILD.md](BUILD.md)；验证范围：[VALIDATION.md](VALIDATION.md)。

以下记录保留各阶段完成时的范围和当时计划；2026-09-27 的 K=4 主线决策取代旧方向，
下文“下一步”不再代表当前队列。提交状态以 Git 为准。

2026-09-24 决策：确定“512 重点优化、768/1024 正确性与扩展验证”，实板放在上板前工作之后。
本次保留关机前 94 条记录，完成其余 341 次执行的 44 个批次，并经严格汇总确认三组各 145 条。
逐例日志、映射、输入哈希和便携工程证据已保存；未进行 64 KiB 实现、加速器集成或实板测试。
本轮未提交 Git，提交状态以工作区为准。

2026-09-25：独立插桩镜像完成 19 批、145 条 RTL 回归；正式软件基线、第三方库、CPU/HLS
原文件保持不变。阶段 CSV、完整统计、构建与批次哈希已归档，新增可断点续跑入口。
未进行新综合/实现、硬件接入或实板操作，修改仍未提交。

2026-09-25（CPU 接入前快照）：完成标准库/加速器接口审计；旧 HLS 明确标记为 legacy baseline。新建
`hls/mlkem512_basemul_k2/`，以独立 testbench 覆盖零值、规范值、signed lazy 边界和
100 组确定性随机输入，C 仿真 103/103 通过；Vitis HLS 2024.2 短路径综合通过，得到
137 cycles、II=1 和估算 Fmax 150.83 MHz；该快照当时尚未进行完整 Vivado 工程接入、
AXI 适配、CPU 接入或官方 KAT 硬件回归，后续记录已补充这些结果。

2026-09-25 后续：独立 MMIO/BRAM/BIST 验证与 Vivado 实现完成，保存
`vivado/mlkem512_basemul_k2/basemul.xpr`、`release/mlkem512_basemul_k2/` 和
`results/accelerator_interface/` 中的证据。现有 CPU baseline 保持不变；RV32IM-fast 的
145 条 ML-KEM-512 官方 KAT 已计入搬运、等待和读回成本，结果为 CPU+PQC 697,154,629
cycles 对 CPU-only 692,273,249 cycles（0.9930×）。下一步应降低接口开销，再开展
768/1024 扩展和新的实现对照。
