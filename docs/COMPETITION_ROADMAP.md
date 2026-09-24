# ML-KEM FPGA 竞赛路线图

## 1. 项目定位

项目最终要交付一个面向资源受限 PYNQ-Z2 的 ML-KEM 端到端软硬件协同加速系统。

核心卖点不应只是“在 FPGA 上实现了 NTT”，而应是：

> 在 PYNQ-Z2 资源约束下，以 FIPS 203/ACVP 标准工作负载为依据，建立 RV32I/RV32IM 软件基线，设计存储—计算协同的可扩展多项式加速器，并用统一的正确性、性能、资源、时序、功耗和安全证据证明设计取舍。

硬件不针对某一个 KAT 输入做特化。官方 KAT 用于标准正确性和真实工作负载验证；加速器面向所有合法 ML-KEM 多项式输入，通用支持 NTT、BaseMul、INTT 和模约减。

最终成果需要回答五个问题：

1. 软件 baseline 是否实现了完整 ML-KEM，而不是只测一个局部函数？
2. 硬件加速器是否保持 FIPS 203 结果正确？
3. 加速的是计算，还是只是把时间转移到了数据搬运和 CPU 轮询？
4. 性能提升付出了多少 LUT、FF、BRAM、DSP、功耗和接口复杂度？
5. 设计是否具有常数时间、参数可配置、可复现和可迁移的工程属性？

## 2. 当前基线和边界

当前仓库已经完成“多项式乘法级软件 baseline”，还没有完成“完整 ML-KEM 标准级 baseline”。

| 已有内容 | 位置 | 作用 | 状态 |
|---|---|---|---|
| RV32I 软件多项式乘法 | firmware/cpu_baseline/ | 无 M 扩展的 CPU 对照 | 已完成 |
| RV32IM 迭代/快速软件对照 | firmware/cpu_baseline/ | 评估 CPU 乘法实现影响 | 已完成 |
| 8 组边界、稠密和随机输入 | tb/software/ | 可重复的局部回归与周期测试 | 已完成 |
| 独立负卷积 oracle | scripts/cpu_baseline/generate_vectors.py | 防止 TB 和软件共用同一错误 | 已完成 |
| CPU-only PicoRV32 系统 | rtl/benchmark/ | 隔离 CPU 软件性能 | 已完成 |
| CPU-only Vivado 工程 | vivado/cpu_baseline_* | 同条件资源、时序和 bitstream 对照 | 已完成 |
| 原有 NTT/BaseMul/INTT 加速器 | rtl/accelerator/、hls/ | 后续硬件主线 | 保持不动 |
| 原有 CPU+加速器系统 | rtl/system/、rtl/board/ | 后续端到端集成入口 | 待接入标准软件 |

当前数据记录在 [性能台账](BENCHMARKS.md) 和 [CPU 测量协议](CPU_BENCHMARK_PROTOCOL.md) 中。当前 8 组输入来自本项目，具有回归价值，但不是官方 KAT，因此当前结果应称为“软件多项式乘法 baseline”，不能称为完整 ML-KEM 官方 baseline。

## 3. 最终系统和公平对照

最终需要建立三层实验对象：

| 对照组 | 内容 | 用途 |
|---|---|---|
| 软件组 | RV32I、RV32IM 迭代、RV32IM 快速完整 ML-KEM | CPU baseline |
| 集成组 | 相同 CPU 加现有 MMIO/AXI 多项式加速器 | 未优化硬件系统 baseline |
| 优化组 | 存储协同、多 PE、低开销接口版本 | 最终设计 |

三组必须使用相同的 FIPS 203 参数集、输入数据、输出检查和计时边界。必须同时报告：

- 完整 KeyGen、Encaps、Decaps 延迟；
- 多项式乘法端到端延迟；
- 加速器核心延迟；
- CPU 写入、启动、等待、读回和校验开销；
- LUT、FF、BRAM、DSP、Fmax/WNS、功耗和能效；
- 正确性、常数时间和故障检测结果。

端到端加速比定义为：

    同配置软件完整 KEM 周期 / CPU+加速器完整 KEM 周期

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

状态：未开始。

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

状态：未开始。

工作内容：

- 将参考实现改造成 freestanding C；
- 编译 RV32I、RV32IM 迭代和 RV32IM 快速三种配置；
- 处理矩阵生成、采样、压缩/解压、噪声多项式、SHAKE/Keccak 和多项式运算；
- 统一 RAM、栈、输入输出和计时布局；
- 如果 16 KiB 不足，三组统一扩大 RAM，并记录 BRAM 成本；
- 在 CPU 仿真中逐字节检查官方 KAT 结果。

出口条件：

- 三种 CPU 配置通过同一批 KAT；
- 记录总周期、阶段周期、代码大小、RAM、栈深度和 M 指令统计；
- 资源和时序报告来自同一版本 RTL 和同一约束。

交付物：firmware/mlkem_baseline/、CPU 工程、results/official_baseline/。

### M3：现有加速器端到端接入

状态：未开始。

工作内容：

- 保持 rtl/accelerator/ 和 HLS 生成快照不变；
- 只替换软件多项式乘法调用为现有 MMIO/AXI 控制路径；
- 保留 CPU 侧输入写入、启动、轮询、读回和校验；
- 使用官方 KAT 检查最终结果；
- 同时测量 Core、Call 和完整 KEM 三种边界。

出口条件：

- 官方 KAT 在 CPU+加速器系统中通过；
- 明确计算、搬运、等待和校验各占多少周期；
- 得到未经优化的硬件系统 baseline。

交付物：加速器适配层、板级/RTL 仿真、results/accelerator_baseline/。

### M4：存储—计算协同优化

状态：未开始。主创新方向。

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
- ML-KEM-512/768/1024 的负载差异。

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

状态：未开始。

工作内容：

- 烧录可复现 bitstream；
- 完成官方 KAT 实板验证；
- 采集端到端周期和板级功耗；
- 提供统一的 Python/寄存器调用示例；
- 展示软件、未优化加速器、优化加速器三组切换。

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

所有配置必须统一：

- FPGA 器件、Vivado 版本和时钟约束；
- C 源码、编译优化和 ABI；
- RAM 容量、栈空间和存储接口；
- KAT 输入、随机种子和正确性检查；
- 计时起点和终点；
- 是否包含数据搬运、轮询、校验和输出。

每个 workload 至少记录最小值、平均值、中位数、最大值或 P95。不能只报告最好的一次运行。局部多项式周期和完整 KEM 周期必须分开，Core、Call 和端到端数据不得混加。

## 6. 竞赛中最有价值的主创新

最终建议把主创新凝练成：

> 面向 PYNQ-Z2 资源约束的 ML-KEM 存储—计算协同架构：通过 BRAM 分 bank、数据搬运与计算重叠、可扩展多 PE 和低开销 CPU 接口，在 FIPS 203/ACVP 标准工作流下实现可复现的端到端性能—资源—能效 Pareto 优化。

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

- [x] 固定 FIPS 203/ACVP 官方 KAT 来源和哈希；
- [x] 完成主机端 ML-KEM-512/768/1024 KAT；
- [ ] 评估完整软件实现的 RAM、代码和栈需求；
- [ ] 移植 RV32I/RV32IM 完整软件 baseline；
- [ ] 建立官方 KAT 的多项式操作数 trace；
- [ ] 接入现有多项式加速器；
- [ ] 完成 CPU+加速器端到端基线；
- [ ] 量化搬运、等待和计算瓶颈；
- [ ] 实现双缓冲、BRAM bank 和批量接口；
- [ ] 扫描 P1/P2/P4/P8 多 PE 配置；
- [ ] 加入常数时间和故障检测；
- [ ] 支持三种 ML-KEM 参数集；
- [ ] 完成 PYNQ-Z2 实板验证；
- [ ] 固化最终报告、视频和可复现工程。

路线图只记录目标、阶段门和待测字段；实际测量数值写入 [BENCHMARKS.md](BENCHMARKS.md)，构建命令写入 [BUILD.md](BUILD.md)，验证证据写入 [VALIDATION.md](VALIDATION.md)，目录规则写入 [STRUCTURE.md](STRUCTURE.md)。

M0/M1 的主机端交付物已经落地：官方向量位于
`vectors/official_kat/acvp/`，结构检查入口为 `scripts/kat/validate_acvp_json.py`，参考
回归入口为 `scripts/kat/run_host_acvp.ps1`，435 个用例的日志位于
`results/official_reference/`。这一步仍不宣称 PicoRV32 或 FPGA 系统通过标准 KAT。
