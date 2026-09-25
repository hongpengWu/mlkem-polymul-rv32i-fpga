# 官方 KeyGen 在 PicoRV32 上的首例证据

记录日期：2026-09-24。Vivado/XSim 2024.2；ML-KEM-512、FIPS203、tgId=1、tcId=1。
这是 CPU RTL 执行新编译 RISC-V 固件的结果，不是主机直接运行 C 的结果。
无 PQC 加速器参与；未做本配置的布局布线或实板运行。

| 文件 | 用途 |
|---|---|
| `summary.md` / `summary.csv` | 三配置可读表格 / 数据 |
| `summary.json` | 计时边界、动态指令、内存和证据 SHA-256 |
| `build_manifest.json` | 编译命令、源文件/镜像/ELF/libgcc SHA-256、ISA 和链接边界 |
| `*_size.txt` / `*_stack_frames.txt` | 链接段统计 / GCC 单函数栈帧统计（不是调用链峰值） |
| `<config>/simulate.log` | 真实 CPU 原始仿真结果；最终必须出现 `MLKEM_KEYGEN_PASS` |
| `negative_check/` | 临时错字节注入被拒绝的预期失败证据，与正常 KAT 结果分开 |

上游 `mlkem-native` 固定便携 C 源码逐字节保留在 `third_party/mlkem-native/`，不启用
native 后端，不使用 LTO。官方 `d || z` 输入打包进固件，预期 `ek/dk` 只交给 TB。
CPU 通过原 AXI/XPM RAM 通路执行算法；没有由 TB 代算，也没有跳过 CPU 算术。

每次 KeyGen 的两次 `rdcycle` 由 TB 观察真实执行边沿，实际 M 指令只在该窗口计数。
完整算法周期包含调用与库内默认临时数据清零，排除启动、种子准备、结果串流和 TB 校验；
空区间 4 周期不扣除。`total_sim_cycles` 包含外围工作，不能代替 KeyGen 周期。

三组统一 64 KiB RAM，链接器为栈保留 16 KiB；最低 SP 表示本例观测峰值，不能代替
全参数集和全部输入的最坏情况分析。`binary_bytes` 是有效代码/常量/初始化数据长度，
`.mem` 则补零至完整 64 KiB。`static_end` 还含 BSS。

当前只有每配置一次 KeyGen/一个用例，不是完整 KEM、全 KAT、性能分布或 NIST 认证。
下一步先扩展 Encaps/Decaps，再扩展向量和参数集。复现命令见 [BUILD.md](../../../docs/BUILD.md)。
