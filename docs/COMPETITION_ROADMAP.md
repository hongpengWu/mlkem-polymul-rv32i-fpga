# ML-KEM FPGA 竞赛路线图

更新日期：2026-09-27。最新完成情况与近期执行顺序见 [项目进度](PROJECT_STATUS.md)。

## 1. 项目定位

项目最终要交付一个面向资源受限 PYNQ-Z2 的 ML-KEM 端到端软硬件协同加速系统。

核心卖点不应只是“在 FPGA 上实现了 NTT”，而应是：

> 在 PYNQ-Z2 资源约束下，以 ML-KEM-1024（K=4）为优化与展示主线，优先评估 Keccak/FIPS 202 主导工作量候选，建立同 CPU、同 RAM 的软硬件端到端对照，并以官方 RTL KAT、周期和系统资源/时序证据证明设计取舍。ML-KEM-512（K=2）冻结为历史对照，ML-KEM-768（K=3）后置扩展。

硬件不针对某一个 KAT 输入做特化。官方 KAT 用于标准正确性和真实工作负载验证。
当前主加速器范围不受旧 BaseMul 限制；Keccak/FIPS 202 核须覆盖所用 SHAKE128/256、
SHA3-256/512 及流式上下文需求，逐位保持标准结果。多项式协同是否值得加入由 K=4 的
负载、端到端和资源报告决定，不预设 NTT/BaseMul/INTT 或多 PE 都必须硬件化。

### 已确认的参数集范围

| 范围 | ML-KEM-1024（K=4） | ML-KEM-512（K=2） | ML-KEM-768（K=3） |
|---|---|---|---|
| 安全类别与定位 | NIST 类别 5，当前主线 | NIST 类别 1，冻结历史对照 | NIST 类别 3，后置扩展 |
| 所选官方向量回归 | fast CPU 145/145；加速系统待做 | 三种 CPU 及 fast CPU+BaseMul 各 145/145 已保存 | fast CPU 145/145；加速扩展后置 |
| RAM / 栈 | 128 / 32 KiB | 64 / 16 KiB | 128 / 32 KiB |
| 阶段分析、HLS 和接口优化 | 报告驱动逐位等价 HLS，随后打包/批量接口 | 保留阶段分析及 0.9930× 端到端历史证据 | 最终架构代表性验证 |
| CPU＋加速器正确性 | 完整官方 RTL KAT，真实硬件调用 | 冻结已完成记录 | 独立验证，不能沿用 CPU-only 结果 |
| 最终展示 | 主展示对象 | 历史对照 | 扩展能力证据 |

三者均使用 256 系数多项式和模数 3329，向量维度及部分采样/压缩参数不同。
K=4 的平台适配必须由实测延迟、存储需求和实现报告支撑。K=2 profiling 的 Keccak
71%–81% 占比仅适用于 K=2，K=4 占比尚未测量。当前先做 HLS、接口和系统仿真与实现，
实板放在上板前工作验收之后；旧“512 主线”决策已于 2026-09-27 被取代。
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
2026-09-25 已完成快速乘法 CPU 的 512 全量阶段分析；768/1024 fast CPU 于 2026-09-26
各完成 145/145。K=2 BaseMul 的独立 MMIO/BRAM/BIST 与 Vivado 2024.2 实现已通过，
fast CPU+PQC 官方 KAT 145/145、端到端 0.9930×，现作为冻结历史对照。
详细 K=2 瓶颈见 [阶段分析](MLKEM512_PROFILE.md)，其阶段占比不作为 K=4 实测数据。

K=4 的 `hls/mlkem1024_keccak/` 已支持四种 FIPS 202 模式、HASH/SQUEEZE/CLEAR、
2048/4096 B 的 32-bit BRAM 输入/输出和 26 个 `uint64` 上下文。io0/io1 均通过 C 与
Verilog COSIM 的 109 笔本地 `hashlib` 差分事务，尚不构成官方 ML-KEM KAT。
所选 `opt02` 优化版全 TB 为 75,280 cycles，基线 1,314,553 cycles；HLS 估算优化版
LUT/FF/BRAM18K/DSP = 15,244/15,385/2/0、8.895 ns，基线为
14,612/17,008/2/0、8.622 ns。独立 IP `opt01` 已完成 OOC 布局布线：100 MHz、WNS/WHS +0.279/+0.098 ns、16,885 LUT/15,320 FF；`opt02` 只修正
LOOP_TRIPCOUNT 上界且周期/资源相同；RTL 对比已随报告归档，不作为完整系统或实板通过声明。
见 [HLS 说明](../hls/mlkem1024_keccak/README.md) 和
[结果汇总](../results/hls/mlkem1024_keccak/summary.md)。

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
| 历史 K=2 NTT 域 BaseMul HLS | hls/mlkem512_basemul_k2/ | 冻结的局部计算对照 | C 仿真/综合已通过 |
| 独立 MMIO/BRAM/BIST 硬件路径 | rtl/accelerator/、vivado/mlkem512_basemul_k2/ | 先验证核、存储、控制和板级顶层 | RTL/BIST/100 MHz 实现通过，XPR/bitstream 已保存 |
| K=2 CPU+PQC 集成系统 | results/accelerator_cpu/kat/ | 冻结的端到端对照 | RV32IM-fast 官方 KAT 145/145；0.9930× |
| K=4 Keccak/FIPS 202 HLS | hls/mlkem1024_keccak/ | 当前主线 HLS 候选 | 局部 C/COSIM 差分通过；独立 IP OOC 实现已完成，系统实现待测 |
| K=4 CPU+加速器集成系统 | 后续打包/批量接口与 CPU 驱动 | 当前主线端到端对照 | 待接入、官方 RTL KAT 与系统实现 |

当前数据记录在 [性能台账](BENCHMARKS.md) 和 [CPU 测量协议](CPU_BENCHMARK_PROTOCOL.md) 中。
原 8 组输入来自本项目，仍作为“软件多项式乘法 baseline”；历史官方 KeyGen 单例独立记账。
当前完整 512 API 结果见 [全量汇总](../results/official_baseline/mlkem512/summary.md) 和
[512 测量协议](MLKEM512_BENCHMARK_PROTOCOL.md)；已包含 RV32IM-fast＋K=2 加速器 145 条
RTL仿真证据；另已完成768/1024 fast CPU-only各145条，
K4 CPU+加速器系统待集成验证，K3 硬件扩展后置。K3/K4 采用128 KiB RAM/32 KiB栈，
512保持64/16 KiB。

## 3. 最终系统和公平对照

最终需要建立三层实验对象：

| 对照组 | 内容 | 用途 |
|---|---|---|
| 软件组 | RV32I、RV32IM 迭代、RV32IM 快速完整 ML-KEM | CPU baseline |
| 集成组 | 相同 CPU 与 RAM，加 K=4 Keccak/FIPS 202 加速器及打包/批量接口 | 首个完整硬件系统 baseline |
| 优化组 | 报告驱动的 HLS、缓冲、批量处理及适用协同版本 | 最终设计 |

同一对照实验中的三组必须使用相同的 FIPS 203 参数集、输入数据、输出检查和计时边界。
以下详细分解以 K=4 为主；K=2 保留历史指标，K=3 后置验证最终选定架构：

- 完整 KeyGen、Encaps、Decaps 延迟；
- Keccak/FIPS 202 调用与其他主要阶段的周期；
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
- 确定完整 API、加速器 Call 和 Core 三种计时边界；全 HLS testbench 周期另行记录。

出口条件：

- 官方向量有来源与哈希；
- 三种计时边界写入协议；
- 后续结果均能追溯到源码、工具、输入和 bitstream 哈希。

交付物：vectors/official_kat/、来源清单、更新后的 BENCHMARKS.md。

### M1：主机端完整 FIPS 203 参考实现

状态：主机三参数集的 435 项官方回归已通过；K=4 加速范围对应的调用/context trace 待建立。

工作内容：

- 在主机上完成 ML-KEM-512/768/1024；
- 覆盖 KeyGen、Encaps、Decaps；
- 通过官方 KAT 检查公钥、私钥、密文和共享密钥；
- 记录参考实现版本和编译环境。

出口条件：

- 所有选定官方 KAT 通过；
- 每个结果都有输入和输出哈希；
- 参考实现可以导出选定加速调用的输入、上下文和预期输出，用于接口 oracle。

交付物：主机参考程序、KAT 回归脚本、results/official_reference/。

### M2：PicoRV32 完整软件 baseline

状态：进行中。2026-09-25 已完成三配置各 145 条 ML-KEM-512 官方记录及快速 CPU 阶段 profiling，每配置逐字节
核对 148,160 B 输入和 101,760 B 输出，并验证错误输出会被拒绝。统一 64 KiB RAM、
16 KiB 栈，最大观测算法栈为 12,928 B；保留可重建的仿真工程与完整批次证据。
512 API 周期分布、动态 M 计数、阶段占比和内存指标已汇总，当前不包含 64 KiB 配置的实现/bitstream。

K3/K4 的 RV32IM-fast CPU-only 也均已 145/145 通过，使用 128 KiB RAM / 32 KiB 栈。
K=4 算法周期 1,699,294,360、最大观测栈 24,464 B；K=3 对应
1,112,525,793 cycles、18,432 B。K=4 阶段占比尚未测量。

当前先完成 **K=4 RV32IM-fast＋软件** 与 **相同 CPU、128/32 KiB RAM/栈＋加速器**
的未插桩对照；独立 profiling 须量化扰动，不能替代正式基线。RV32I/迭代乘法消融与
K=3 硬件扩展后置；K=2 已有基线和阶段分析冻结保存，不继续主线优化。

工作内容：

- 将参考实现改造成 freestanding C；
- 编译 RV32I、RV32IM 迭代和 RV32IM 快速三种配置；
- 处理矩阵生成、采样、压缩/解压、噪声多项式、SHAKE/Keccak 和多项式运算；
- 统一 RAM、栈、输入输出和计时布局；
- 同参数集软件/硬件对照统一 RAM/栈，记录其 BRAM 成本；
- 在 CPU 仿真中逐字节检查官方 KAT 结果。

出口条件：

- K=4 主线 CPU 完成所选 145 项官方记录，按修订/操作/参数集登记覆盖；其他 CPU 消融后补；
- 三参数集保留总周期、代码大小、RAM、栈深度和 M 指令统计，K=4 补齐阶段周期；
- 资源和时序报告来自同一版本 RTL 和同一约束。

交付物：firmware/mlkem512_suite/、后续参数集驱动、CPU 工程、results/official_baseline/。

### M3：K=4 精确 HLS 优化与端到端接入

状态：进行中。K=4 Keccak/FIPS 202 的 io0/io1 局部 C/Verilog COSIM 差分已通过，
独立 IP OOC 布局布线已通过当前时钟约束；打包/批量接口、CPU 集成和官方 RTL KAT 尚未完成。
K=2 的独立实现与 0.9930× 集成结果只作为历史参考。

工作内容：

- 先基于报告逐项优化 HLS，保持 FIPS 202 逐位结果，区分 C 仿真、COSIM、HLS 估算和物理实现；
- 明确四模式、HASH/SQUEEZE/CLEAR、26 个 `uint64` 上下文及边界输入的协议；
- 以 32-bit 打包缓冲、批量命令降低接口开销，之后接入 RV32IM-fast 标准软件调用；
- 对 K=4 官方 145 条记录证明真实硬件调用、输入/输出及 API 返回值一致；
- 用相同 CPU、128 KiB RAM / 32 KiB 栈的未插桩镜像测量 Core、Call 和完整 API，计入搬运/等待。

出口条件：

- K=4 官方 KAT 在 CPU+加速器系统中 145/145 通过，本地 `hashlib` 差分不能替代；
- 明确计算、搬运、等待和校验各占多少周期；
- 得到未经优化的 CPU+PQC 硬件系统 baseline。

当前交付物：`hls/mlkem1024_keccak/` 与 `results/hls/mlkem1024_keccak/`；后续补充
K=4 CPU 驱动、RTL 接口、官方回归与系统实现证据。现有 `rtl/accelerator/`、
`vivado/mlkem512_basemul_k2/`、`results/accelerator_interface/` 和
`results/accelerator_cpu/kat/` 继续作为 K=2 历史证据保存。

### M4：存储—计算协同优化

状态：接口与系统优化待开始；K=4 局部 HLS 优化已进入报告驱动验证。以 ML-KEM-1024 为主要工作负载。

设计内容：

- 输入/输出按 32-bit 打包，减少搬运事务，保持字节顺序和 SHAKE 上下文正确；
- 基于 HLS 报告评估 Keccak lane banking、轮级复用、流水和吸收/置换/输出组织；
- 批量命令、共享缓冲及适用的 ping-pong 重叠，减少调用和轮询成本；
- 保持低资源基线，只有端到端收益与资源证据支持时才扩大并行度或加入多项式协同。

出口条件：

- Call/Core 差距得到量化解释；
- 搬运、等待和计算的周期分解可重复；
- 至少一种优化降低端到端周期；
- 官方 KAT 和局部 workload 全部通过。

交付物：优化 RTL/HLS、接口协议、带宽统计、前后对照报告。

### M5：K=4 设计空间和 Pareto 选择

状态：未开始。

在系统端到端和资源基线建立后，依据瓶颈选择扫描维度，不预设多 PE 为必选结构：

| 配置 | 目标 |
|---|---|
| Keccak 轮级复用/流水 | 比较周期、时钟和逻辑资源 |
| lane banking 与缓冲组织 | 比较访存并行度和 BRAM 成本 |
| 批量大小及上下文调度 | 比较调用成本和端到端周期 |
| 适用的并行或多项式协同 | 仅在瓶颈和资源报告支持时评估 |

每组统一执行 Vivado 2024.2 综合、布局布线和时序分析，收集：

- 延迟、吞吐率和 Fmax；
- LUT、FF、BRAM、DSP；
- 功耗和每次 KEM 能量；
- AXI/BRAM 带宽利用率；
- K=4 的详细负载与阶段分解，最终选定架构下 K=3 的代表性负载差异。

设计空间扫描以 K=4 为主；K=2 历史实现冻结，K=3 后置验证，不要求重复每轮扫参。
每次算法/接口变更须通过相应局部回归和已接入参数集的官方回归。

出口条件：

- 输出吞吐率—LUT、延迟—BRAM/DSP、能效—资源三类 Pareto 图；
- 根据资源约束选择一个 Pareto 前沿配置；
- 不以并行度最大或单个 Core 周期最少作为默认最优方案。

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
- 可配置的 SHAKE/SHA3 模式和上下文；
- 对最终选定并行度与缓冲容量进行版本管理；
- 多项式协同若进入最终架构，再验证其相应配置；
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
- 以 K=4 展示软件、集成基线、优化加速器三组切换，补充 K=2 历史和 K=3 扩展证据。

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

每个 workload 至少记录最小值、平均值、中位数、最大值或 P95。不能只报告最好的一次运行。
局部 HLS 全 TB、Core、Call 和完整 API 周期必须分开，不得混加或将全 TB 加速比当作完整 KEM 加速比。

512/768/1024 如采用不同 RAM 或构建配置，应独立记录，不能将其差异归因于算法参数本身。
用例回归完成前只报告实际覆盖数；确定性单例结果不能作为分布统计。
官方公开向量离线通过只证明已覆盖结果一致性，不构成正式 CAVP 算法验证或 FIPS 140-3 / CMVP 模块认证。

## 6. 竞赛中最有价值的主创新

最终建议把主创新凝练成：

> 面向 PYNQ-Z2 资源约束的 ML-KEM-1024 软硬件协同架构：以报告驱动且逐位等价的 Keccak/FIPS 202 HLS、打包缓冲与批量 CPU 接口降低端到端成本，用官方 RTL KAT、同配置未插桩周期及系统资源/时序证明优化，并保留 K=2 历史对照与 K=3 扩展证据。

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
7. 展示实际评估架构的资源—性能 Pareto 图；
8. 展示 BRAM 带宽和数据重叠结构；
9. 展示 bitstream、日志和源码哈希；
10. 说明功耗、安全和资源权衡。

## 8. 当前执行队列

当前完成点（2026-09-27）：K=2 的三种 CPU 各 145/145、CPU+BaseMul 145/145 与
0.9930× 结果冻结保存；K3/K4 fast CPU 各 145/145 已完成。K=4 Keccak/FIPS 202 HLS
的 io0/io1 C/COSIM 局部差分通过，独立 IP OOC 实现已完成。当前没有 K=4 加速官方 KAT、
端到端加速比或系统实现通过结论。自动续跑 `pqc-kat` 为 **PAUSED，60 分钟间隔**。

- [x] 确定 K=4 主线、K=2 冻结历史、K=3 后置扩展，实板最后；
- [x] 固定 FIPS 203/ACVP 来源、哈希和主机三参数集 435 项回归；
- [x] 保存 K=2 CPU/加速回归、阶段分析及独立实现证据；
- [x] 完成 K3/K4 RV32IM-fast CPU-only 官方 145/145 与基本周期/内存测量；
- [x] 建立 K=4 四模式、HASH/SQUEEZE/CLEAR HLS 和本地差分集，io0/io1 C/COSIM 109 笔事务通过；
- [x] 完成首轮独立 HLS OOC 物理实现与精确功能/周期对比；后续优化按系统瓶颈推进；
- [ ] 建立 K=4 官方调用/context trace 与打包/批量接口，接入标准 CPU 固件；
- [ ] 完成 K=4 CPU+加速器官方 RTL KAT 145/145，核验真实硬件调用；
- [ ] 完成同 RV32IM-fast、128 KiB RAM / 32 KiB 栈的未插桩端到端对照，独立测量 K=4 阶段占比；
- [ ] 完成 K=4 软件/加速系统同约束资源和时序报告，依据瓶颈选择进一步优化；
- [ ] 后置验证 K=3 扩展与其他 CPU 消融，保留独立官方回归和内存配置记录；
- [ ] 完成适用常数时间、故障检查和上板前系统/产物验收；
- [ ] 最后完成 PYNQ-Z2 实板验证、演示和可复现证据包。

路线图记录目标、范围、阶段门和待测字段；当前进度汇总见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。
实际测量数值写入 [BENCHMARKS.md](BENCHMARKS.md)，构建命令写入 [BUILD.md](BUILD.md)，
验证证据写入 [VALIDATION.md](VALIDATION.md)，目录规则写入 [STRUCTURE.md](STRUCTURE.md)。

M0/M1 的主机端交付物已经落地：官方向量位于
`vectors/official_kat/acvp/`，结构检查入口为 `scripts/kat/validate_acvp_json.py`，参考
回归入口为 `scripts/kat/run_host_acvp.ps1`，435 个用例的日志位于
`results/official_reference/`。主机结果不计入 PicoRV32 覆盖；历史 M2 首例独立保存于
`results/official_baseline/keygen512_tc1/`，当前完整 512 回归保存于
`results/official_baseline/mlkem512/`。后者只覆盖指定版本的 512 官方记录，
不能用于证明其他参数集、实板或正式认证。512 CPU＋加速器和768/1024 fast CPU已有
各自独立证据；K=4 HLS 局部差分与 CPU+加速器官方验证须分开记账，K=3 硬件扩展后置。
