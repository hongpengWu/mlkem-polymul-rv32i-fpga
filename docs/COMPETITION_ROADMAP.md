# ML-KEM FPGA 竞赛路线图

更新日期：2026-09-25。最新完成情况与近期执行顺序见 [项目进度](PROJECT_STATUS.md)。

## 1. 项目定位

项目最终要交付一个面向资源受限 PYNQ-Z2 的 ML-KEM 端到端软硬件协同加速系统。

核心卖点不应只是“在 FPGA 上实现了 NTT”，而应是：

> 在 PYNQ-Z2 资源约束下，以 ML-KEM-512 为主要优化对象、以 ML-KEM-768/1024 验证扩展能力，建立 RV32I/RV32IM 软件基线，设计存储—计算协同的可扩展多项式加速器，并用 FIPS 203/ACVP 正确性回归及性能、资源、时序、功耗和安全证据证明设计取舍。

硬件不针对某一个 KAT 输入做特化。官方 KAT 用于标准正确性和真实工作负载验证；加速器面向所有合法 ML-KEM 多项式输入，通用支持 NTT、BaseMul、INTT 和模约减。

### 已确认的参数集范围

| 范围 | ML-KEM-512 | ML-KEM-768 / 1024 |
|---|---|---|
| 安全类别 | NIST 类别 1，目标应用定位 | NIST 类别 3 / 5 |
| 所选官方向量回归 | 完整执行 | 同样完整执行 |
| 三种 CPU 的基本周期、代码、RAM 和栈 | 完整测量 | 同样测量，支撑参数选择 |
| 阶段分析、接口和存储优化、多 PE 扫参 | 主线，重点展开 | 最终架构补充代表性结果，不要求重复每轮扫参 |
| CPU＋加速器正确性 | 完整流程验证 | 验证兼容性，不能沿用纯软件通过记录 |
| 最终展示 | 主展示对象 | 三参数集功能与扩展能力证据 |

三者均使用 256 系数多项式和模数 3329，向量维度及部分采样/压缩参数不同。
512 的主线选择已确定，但其平台适配理由仍要由实测延迟和存储需求支撑；不预先认定
PYNQ-Z2 不能运行 768/1024。当前阶段先做仿真与实现，实板放在上板前工作验收之后。
支持三个参数集不等同于支持多种密码算法；官方公开向量通过也不等同于正式认证。

最终成果需要回答五个问题：

1. 软件 baseline 是否实现了完整 ML-KEM，而不是只测一个局部函数？
2. 硬件加速器是否保持 FIPS 203 结果正确？
3. 加速的是计算，还是只是把时间转移到了数据搬运和 CPU 轮询？
4. 性能提升付出了多少 LUT、FF、BRAM、DSP、功耗和接口复杂度？
5. 设计是否具有常数时间、参数可配置、可复现和可迁移的工程属性？

## 2. 当前基线和边界

当前仓库已经完成“多项式乘法级软件 baseline”、三参数集共 435 项主机官方向量回归，
以及三种 PicoRV32 配置各 145 条 ML-KEM-512 官方记录的完整 API 基线。
2026-09-25 已完成快速乘法 CPU 的 512 全量阶段分析；768/1024 fast CPU于2026-09-26各完成145/145；M2仍待补齐其他CPU配置
和 64 KiB 配置实现。新 BaseMul 的独立 MMIO/BRAM/BIST 与 Vivado 2024.2 实现已通过，
RV32IM-fast CPU+PQC 的 145 条 ML-KEM-512 官方 KAT 也已完成；端到端为 0.9930×，
下一步应先降低搬运和轮询开销，再扩展多 PE。详细瓶颈与接入任务见 [阶段分析](MLKEM512_PROFILE.md)。

| 已有内容 | 位置 | 作用 | 状态 |
|---|---|---|---|
| RV32I 软件多项式乘法 | firmware/cpu_baseline/ | 无 M 扩展的 CPU 对照 | 已完成 |
| RV32IM 迭代/快速软件对照 | firmware/cpu_baseline/ | 评估 CPU 乘法实现影响 | 已完成 |
| 8 组边界、稠密和随机输入 | tb/software/ | 可重复的局部回归与周期测试 | 已完成 |
| 独立负卷积 oracle | scripts/cpu_baseline/generate_vectors.py | 防止 TB 和软件共用同一错误 | 已完成 |
| CPU-only PicoRV32 系统 | rtl/benchmark/ | 隔离 CPU 软件性能 | 已完成 |
| CPU-only Vivado 工程 | vivado/cpu_baseline_* | 同条件资源、时序和 bitstream 对照 | 已完成 |
| 主机 ML-KEM 官方回归 | results/official_reference/ | 三参数集 KeyGen/Encaps/Decaps 等 435 用例 | 已通过，CPU RTL 覆盖独立记录 |
| PicoRV32 ML-KEM-512 官方全集 | firmware/mlkem512_suite/、results/official_baseline/mlkem512/ | 标准便携 C 的完整 API 调用基线 | 三组各 145 条已通过，64 KiB RAM，仅 RTL 仿真 |
| 历史官方 KeyGen 首例 | firmware/mlkem_baseline/、results/official_baseline/keygen512_tc1/ | 首次标准算法执行闭环，独立保留 | 三组 tcId=1 已通过，不替代当前全量分布 |
| 新 K=2 NTT 域 BaseMul HLS | hls/mlkem512_basemul_k2/ | 新硬件主线的计算核心 | C 仿真/综合已通过 |
| 独立 MMIO/BRAM/BIST 硬件路径 | rtl/accelerator/、vivado/mlkem512_basemul_k2/ | 先验证核、存储、控制和板级顶层 | RTL/BIST/100 MHz 实现通过，XPR/bitstream 已保存 |
| 新 CPU+PQC 集成系统 | 基于已验证 adapter 新建 CPU 集成系统 | 端到端公平对照入口 | RV32IM-fast 官方 KAT 145/145；当前 0.9930×，待优化 |

当前数据记录在 [性能台账](BENCHMARKS.md) 和 [CPU 测量协议](CPU_BENCHMARK_PROTOCOL.md) 中。
原 8 组输入来自本项目，仍作为“软件多项式乘法 baseline”；历史官方 KeyGen 单例独立记账。
当前完整 512 API 结果见 [全量汇总](../results/official_baseline/mlkem512/summary.md) 和
[512 测量协议](MLKEM512_BENCHMARK_PROTOCOL.md)；已包含 RV32IM-fast＋K=2 加速器 145 条
RTL仿真证据；另已完成768 fast CPU-only 145条，1024 CPU-only运行中，
K3/K4加速硬件仍待移植验证。扩展参数采用128 KiB RAM/32 KiB栈，512保持64/16 KiB。

## 3. 最终系统和公平对照

最终需要建立三层实验对象：

| 对照组 | 内容 | 用途 |
|---|---|---|
| 软件组 | RV32I、RV32IM 迭代、RV32IM 快速完整 ML-KEM | CPU baseline |
| 集成组 | 相同 CPU 加已验证的 native-MMIO 多项式加速器 | 未优化硬件系统 baseline |
| 优化组 | 存储协同、多 PE、低开销接口版本 | 最终设计 |

同一对照实验中的三组必须使用相同的 FIPS 203 参数集、输入数据、输出检查和计时边界。
以下详细分解以 512 为主；768/1024 保留基本指标与最终选定架构的验证：

- 完整 KeyGen、Encaps、Decaps 延迟；
- 多项式乘法端到端延迟；
- 加速器核心延迟；
- CPU 写入、启动、等待、读回和校验开销；
- LUT、FF、BRAM、DSP、Fmax/WNS、功耗和能效；
- 正确性、常数时间和故障检测结果。

端到端加速比定义为：

    同参数集、同输入、同 CPU 配置的软件操作周期 / CPU+加速器同一操作周期

分别对 KeyGen、Encaps、Decaps 计算；若组合成完整工作流，必须明确调用顺序和次数。

Core 周期不包含 CPU 搬运；Call 周期不应再次加上与其重叠的核心周期。

## 4. 分阶段路线和验收门

### M0：冻结工具、标准和测量口径

状态：进行中。

工作内容：

- 固定 FIPS 203 版本和 NIST ACVP/KAT 数据来源；
- 固定 Vivado 2024.2、RISC-V 工具链、器件和时钟约束；
- 保存官方向量原文件、来源 URL、下载日期和 SHA-256；
- 保留当前 8 组自定义向量作为快速回归集；
- 确定完整 KEM、单次多项式和加速器 Core 三种计时边界。

出口条件：

- 官方向量有来源与哈希；
- 三种计时边界写入协议；
- 后续结果均能追溯到源码、工具、输入和 bitstream 哈希。

交付物：vectors/official_kat/、来源清单、更新后的 BENCHMARKS.md。

### M1：主机端完整 FIPS 203 参考实现

状态：主机三参数集的 435 项官方回归已通过；多项式操作数 trace 导出尚未完成，因此阶段门未全部关闭。

工作内容：

- 在主机上完成 ML-KEM-512/768/1024；
- 覆盖 KeyGen、Encaps、Decaps；
- 通过官方 KAT 检查公钥、私钥、密文和共享密钥；
- 记录参考实现版本和编译环境。

出口条件：

- 所有选定官方 KAT 通过；
- 每个结果都有输入和输出哈希；
- 参考实现可以导出每次多项式乘法的操作数。

交付物：主机参考程序、KAT 回归脚本、results/official_reference/。

### M2：PicoRV32 完整软件 baseline

状态：进行中。2026-09-25 已完成三配置各 145 条 ML-KEM-512 官方记录及快速 CPU 阶段 profiling，每配置逐字节
核对 148,160 B 输入和 101,760 B 输出，并验证错误输出会被拒绝。统一 64 KiB RAM、
16 KiB 栈，最大观测算法栈为 12,928 B；保留可重建的仿真工程与完整批次证据。
512 API 周期分布、动态 M 计数、阶段占比和内存指标已汇总，当前不包含 64 KiB 配置的实现/bitstream。

主线已确认：先完成 **RV32IM 快速乘法＋软件** 与 **相同 CPU＋PQC 加速器** 的横向对照，
再补 RV32I、迭代乘法的硬件消融。已有三种 CPU 的软件基线继续保留；完整 M2 的
跨参数集验收仍待补齐，可以与 M3 主线接入分步推进，不用先重复全部配置的优化实验。

1. 已完成 RV32IM 快速乘法配置的 512 独立阶段 profiling，分析 SHAKE/Keccak、采样、
   多项式和压缩开销，与正式未插桩 API 基线对应；入口见 [阶段测量](MLKEM512_PROFILE.md)。
2. NTT 域、Montgomery 缩放、系数范围/布局和向量累加的接口契约与独立 oracle 已建立；
   后续导出官方调用中的中间操作数，再接入新 BaseMul 核。
3. 先完成快速乘法 CPU 两套系统的官方 512 回归、完整 API 加速比、搬运开销和
   64 KiB 配置 Vivado 2024.2 实现，比较同条件资源/时序；旧 16 KiB 实现数字不得替代。
4. 根据阶段占比决定多项式与 Keccak 的加速范围，再进行存储与计算优化。
5. 补齐 RV32I/迭代乘法消融，以及 768/1024 的官方回归、基本周期/内存和最终架构验证。
   同参数集的 CPU 对照保持同一 RAM；跨参数集容量差异明确记录。实板仍放到最后。

工作内容：

- 将参考实现改造成 freestanding C；
- 编译 RV32I、RV32IM 迭代和 RV32IM 快速三种配置；
- 处理矩阵生成、采样、压缩/解压、噪声多项式、SHAKE/Keccak 和多项式运算；
- 统一 RAM、栈、输入输出和计时布局；
- 如果 16 KiB 不足，三组统一扩大 RAM，并记录 BRAM 成本；
- 在 CPU 仿真中逐字节检查官方 KAT 结果。

出口条件：

- 三种 CPU 配置完成固定 435 项主机用例在 CPU 上的对应验证，按修订/操作/参数集登记覆盖；
- 三参数集记录总周期、代码大小、RAM、栈深度和 M 指令统计；512 补齐阶段周期；
- 资源和时序报告来自同一版本 RTL 和同一约束。

交付物：firmware/mlkem512_suite/、后续参数集驱动、CPU 工程、results/official_baseline/。

### M3：新 HLS 端到端接入

状态：进行中。独立 MMIO/BRAM/BIST、Vivado 2024.2 实现和 bitstream 已完成；
PicoRV32 接入和 ML-KEM-512 CPU+PQC 官方 KAT 已完成；当前性能基线为 0.9930×。

工作内容：

- 已完成新 HLS 的独立 native MMIO/BRAM adapter，基址 `0x50001000`；
- 已接入 RV32IM-fast 总线，只替换标准软件 BaseMul 调用，保留 CPU-only baseline；
- 保留 CPU 侧输入写入、启动、轮询、读回和校验；
- 512已跑通完整流程；768 fast CPU官方全集通过，1024 fast CPU分批运行中；K3/K4硬件包装和KAT待做；
- 同时测量 Core、Call 和完整 KEM 三种边界。

出口条件：

- 官方 KAT 在 CPU+加速器系统中通过；
- 明确计算、搬运、等待和校验各占多少周期；
- 得到未经优化的 CPU+PQC 硬件系统 baseline。

当前交付物：`rtl/accelerator/`、`tb/accelerator/`、`vivado/mlkem512_basemul_k2/basemul.xpr`、
`release/mlkem512_basemul_k2/`、`results/accelerator_interface/` 和
`results/accelerator_cpu/kat/`；后续增加搬运优化和参数集扩展。

### M4：存储—计算协同优化

状态：未开始。主创新方向，以 ML-KEM-512 为主要优化工作负载。

设计内容：

- 系数按 16-bit 或打包 32-bit 组织，减少 AXI 事务；
- BRAM 分 bank/interleave，支持多 butterfly 或 BaseMul PE 并行访问；
- ping-pong buffer 重叠当前计算和下一块搬运；
- twiddle factor 放入片上 ROM；
- 在 NTT、BaseMul、INTT 之间建立 FIFO 或片上流；
- 增加批量命令或 DMA 风格接口，减少逐字 MMIO 和 CPU 轮询；
- 保留单 PE 低资源模式。

出口条件：

- Call/Core 差距得到量化解释；
- 搬运、等待和计算的周期分解可重复；
- 至少一种优化降低端到端周期；
- 官方 KAT 和局部 workload 全部通过。

交付物：优化 RTL/HLS、接口协议、带宽统计、前后对照报告。

### M5：多 PE 设计空间和 Pareto 选择

状态：未开始。

配置集合：

| 配置 | 目标 |
|---|---|
| P1 | 单 PE，最低资源 |
| P2 | 双 PE，平衡配置 |
| P4 | 四 PE，高吞吐 |
| P8 | 资源上限探索 |

每组统一执行 Vivado 2024.2 综合、布局布线和时序分析，收集：

- 延迟、吞吐率和 Fmax；
- LUT、FF、BRAM、DSP；
- 功耗和每次 KEM 能量；
- AXI/BRAM 带宽利用率；
- 512 的详细负载与阶段分解，最终选定架构下 768/1024 的代表性负载差异。

PE 数量和存储方案的完整扫参以 512 为主；768/1024 不要求重复每轮扫参，
但影响算法/接口正确性的变更须通过三参数集回归，最终架构补充基本性能与存储结果。

出口条件：

- 输出吞吐率—LUT、延迟—BRAM/DSP、能效—资源三类 Pareto 图；
- 根据资源约束选择一个 Pareto 前沿配置；
- 不以 PE 数量最大作为默认最优方案。

交付物：参数化工程、自动扫参脚本、results/design_space/。

### M6：安全、故障检测和密码敏捷

状态：未开始。

安全内容：

- 固定时延；
- 固定访存模式；
- 无秘密相关分支；
- 模运算路径无数据相关早停；
- CRC、重复计算或范围检查故障检测。

密码敏捷内容：

- ML-KEM-512/768/1024；
- 可替换 twiddle ROM；
- 可配置 PE 数量；
- 可替换模约减模式；
- 统一控制寄存器和版本寄存器。

没有实测功耗采集时，只报告常数时间约束和 RTL 验证，不宣称完整侧信道防护。具备设备后再做 TVLA 或相关功耗分析。

出口条件：

- KAT、随机回归、非法输入和故障注入测试通过；
- 参数配置不会破坏已有结果；
- 安全结论与实测证据范围一致。

### M7：PYNQ-Z2 实板和应用展示

状态：未开始，最后执行。先完成上板前的标准软件/加速系统仿真、适用安全与故障检查、
综合、布局布线、时序检查及匹配产物准备；进度期间不提前安排烧录。

工作内容：

- 烧录可复现 bitstream；
- 完成官方 KAT 实板验证；
- 采集端到端周期和板级功耗；
- 提供统一的 Python/寄存器调用示例；
- 以 512 展示软件、未优化加速器、优化加速器三组切换，补充三参数集正确性结果。

出口条件：

- 仿真、实现和实板结果一致；
- bitstream、输入、日志和板级读回均有哈希；
- 实板演示不依赖手工修改寄存器。

交付物：bitstream、板级日志、烧录说明、应用示例和演示视频。

### M8：最终证据打包

状态：未开始。

证据链：

    标准 KAT 输入哈希
    → 主机参考结果
    → RV32I/RV32IM 软件结果
    → 加速器局部结果
    → CPU+加速器完整结果
    → Vivado 资源/时序/功耗报告
    → bitstream 哈希
    → 性能—资源—安全结论

最终提交必须包含：

- 一键或少步骤重建脚本；
- 正确性日志；
- 周期 CSV；
- LUT/FF/BRAM/DSP/Fmax/WNS 表；
- 功耗或能效证据；
- 设计空间和 Pareto 图；
- 源码、向量、工具和 bitstream 哈希；
- 已知限制和未声明事项。

## 5. 公平实验协议

同参数集、同一轮软件/硬件对照中的配置必须统一：

- FPGA 器件、Vivado 版本和时钟约束；
- C 源码、编译优化和 ABI；
- RAM 容量、栈空间和存储接口；
- KAT 输入、随机种子和正确性检查；
- 计时起点和终点；
- 是否包含数据搬运、轮询、校验和输出。

每个 workload 至少记录最小值、平均值、中位数、最大值或 P95。不能只报告最好的一次运行。局部多项式周期和完整 KEM 周期必须分开，Core、Call 和端到端数据不得混加。

512/768/1024 如采用不同 RAM 或构建配置，应独立记录，不能将其差异归因于算法参数本身。
用例回归完成前只报告实际覆盖数；确定性单例结果不能作为分布统计。
官方公开向量离线通过只证明已覆盖结果一致性，不构成正式 CAVP 算法验证或 FIPS 140-3 / CMVP 模块认证。

## 6. 竞赛中最有价值的主创新

最终建议把主创新凝练成：

> 面向 PYNQ-Z2 资源约束、重点优化 ML-KEM-512 的存储—计算协同架构：通过 BRAM 分 bank、数据搬运与计算重叠、可扩展多 PE 和低开销 CPU 接口，实现可复现的端到端性能—资源—能效 Pareto 优化，并以三个 ML-KEM 参数集的官方公开向量回归验证扩展能力。

加分项是：

- 标准 KAT 全流程验证；
- ML-KEM-512/768/1024 参数敏捷；
- 常数时间和基础故障检测；
- PCPI 自定义指令或命令队列接口；
- 实板功耗和能效测量；
- 自动化扫参和可复现工程。

不要把“支持某一个 KAT 输入”作为创新，也不要把只降低硬件 Core 周期称为端到端加速。

## 7. 竞赛现场展示顺序

1. 展示 FIPS 203 KAT 正确性；
2. 运行 RV32I 软件 baseline；
3. 运行 RV32IM 软件 baseline；
4. 运行 CPU+现有加速器；
5. 展示优化版的端到端周期；
6. 展示 Core/Call/端到端分解；
7. 展示 1/2/4 PE 的资源—性能 Pareto 图；
8. 展示 BRAM 带宽和数据重叠结构；
9. 展示 bitstream、日志和源码哈希；
10. 说明功耗、安全和资源权衡。

## 8. 当前执行队列

当前完成点（2026-09-24）：512 全量回归已完成，RV32I／迭代／快速各 145 条通过。
关机前的 25／31／38 条原始记录与 44 个独立完成批次合并，原始身份无重复或遗漏；
全量日志、映射和哈希见 [512 汇总](../results/official_baseline/mlkem512/summary.md)。
2026-09-25 快速 CPU 的 512 全量阶段分析、标准库接口契约、独立 BaseMul
MMIO/BRAM/BIST、Vivado 实现和 CPU+PQC 官方 KAT 已完成；145 条 RTL 记录全部通过，
端到端为 0.9930×。下一步先降低搬运/轮询开销，再量化同配置资源与时序；完整 M2 仍需
补齐扩展参数集。

- [x] 确定 512 重点优化、768/1024 正确性与基本性能验证的范围，实板放到最后；
- [x] 固定 FIPS 203/ACVP 官方 KAT 来源和哈希；
- [x] 完成主机端 ML-KEM-512/768/1024 KAT；
- [x] 三种 PicoRV32 配置通过官方 ML-KEM-512 KeyGen 首例（仅 RTL 仿真）；
- [x] 建立逐字节 oracle、实际 rdcycle/M 指令观测和错字节拒绝检查；
- [x] 完成 PicoRV32 Encaps/Decaps 首例和 ML-KEM-512 全套对应向量；
- [ ] 完成 PicoRV32 768/1024 对应官方向量回归及基本周期/内存测量；
- [x] 完成 512 完整 API 的 RAM、代码、观测栈和动态 M 指令测量；
- [x] 完成快速 CPU 的 512 独立阶段 profiling（145 条、19 批）；
- [x] 完成新 BaseMul 的接口契约、独立 MMIO/BRAM/BIST 仿真、Vivado 实现和 bitstream；
- [ ] 完成三组 64 KiB CPU 配置的资源、时序和 bitstream；
- [ ] 补齐 768/1024 的完整软件移植和内存需求测量；
- [ ] 建立官方 KAT 的多项式操作数 trace；
- [x] 将新 BaseMul 接入 RV32IM-fast 并通过官方 ML-KEM-512 KAT；
- [ ] 按 Keccak 71%–81% 的实测占比，比较仅多项式、仅 Keccak 与两者协同的端到端收益；
- [x] 完成 CPU+加速器端到端基线；
- [x] 重点量化 512 的搬运、等待和计算瓶颈；当前端到端为 0.9930×，优化尚未开始；
- [ ] 面向 512 实现双缓冲、BRAM bank 和批量接口；
- [ ] 以 512 扫描 P1/P2/P4/P8 多 PE 配置；
- [ ] 加入常数时间和故障检测；
- [ ] 在最终 CPU＋加速器架构复验三参数集，补齐 768/1024 代表性测量；
- [ ] 完成上板前系统回归、综合、布局布线、时序和匹配烧录产物验收；
- [ ] 完成 PYNQ-Z2 实板验证；
- [ ] 固化最终报告、视频和可复现工程。

路线图记录目标、范围、阶段门和待测字段；当前进度汇总见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。
实际测量数值写入 [BENCHMARKS.md](BENCHMARKS.md)，构建命令写入 [BUILD.md](BUILD.md)，
验证证据写入 [VALIDATION.md](VALIDATION.md)，目录规则写入 [STRUCTURE.md](STRUCTURE.md)。

M0/M1 的主机端交付物已经落地：官方向量位于
`vectors/official_kat/acvp/`，结构检查入口为 `scripts/kat/validate_acvp_json.py`，参考
回归入口为 `scripts/kat/run_host_acvp.ps1`，435 个用例的日志位于
`results/official_reference/`。主机结果不计入 PicoRV32 覆盖；历史 M2 首例独立保存于
`results/official_baseline/keygen512_tc1/`，当前完整 512 回归保存于
`results/official_baseline/mlkem512/`。后者只覆盖指定版本的 512 官方记录，
不能用于证明其他参数集、实板或正式认证。512 CPU＋加速器和768 fast CPU已有各自独立证据，
1024 fast CPU仍运行中，K3/K4加速硬件尚待移植与验证。
