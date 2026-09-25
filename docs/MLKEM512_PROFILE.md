# ML-KEM-512 分阶段耗时与加速决策

本实验回答：**RV32IM 快速乘法 CPU 执行完整 ML-KEM-512 时，时间主要花在哪里？**
它为下一步选择硬件加速范围提供依据。正式软件性能基线仍是
[未插桩的 145 条结果](../results/official_baseline/mlkem512/summary.md)。

**2026-09-25 已完成全部 145 条记录、19 个批次。主要瓶颈是 Keccak 置换，
占主要 KEM 操作周期的 71%–81%；多项式算术约占 13%–21%。**
这些比例适用于当前 portable C、RV32IM 快速乘法和存储配置。

## 实验范围与测量方法

- CPU 为 PicoRV32 RV32IM 快速乘法，`MUL/FAST_MUL/DIV=1/1/1`；64 KiB RAM、16 KiB 栈，沿用基线编译器与 `-O3` 优化参数。
- 输入为相同的 145 条固定版本官方 ML-KEM-512 ACVP 记录，覆盖 KeyGen、Encaps、两种 Decaps 和有效/无效密钥检查。预期输出仅供 testbench 比较，不输入 CPU。
- 新固件在 `build/mlkem512_profile/generated/` 中的源码副本加入 42 个函数范围事件；原始第三方库、CPU RTL、加速器和基线固件不修改。可审查的改动保存在 [instrumentation.patch](../results/official_baseline/mlkem512/profile/instrumentation.patch)。
- 每次 API 仍只有原来的开始、结束两次 `rdcycle`。函数进入/退出向现有调试寄存器写标记，testbench 被动累计周期，支持函数嵌套。
- **独占周期**只计入当时最内层函数，各类别加起来等于整个 API 周期；**包含子函数的周期**用于理解调用组成，存在重叠，不能相加。
- 插桩会增加指令、MMIO 访问，也可能改变编译器分配和代码布局。逐例与原基线比较差值，不能把插桩结果替换为正式性能基线，亦不能把全部差值解释为固定的标记成本。

例如，矩阵生成调用 SHAKE，SHAKE 又调用 Keccak。独占统计分别记录矩阵控制、SHAKE 吸收/输出等外围工作、Keccak 置换；矩阵生成的包含子函数周期则涵盖整个调用树。这样既能看完整矩阵生成成本，也不会重复计算 Keccak。

详细事件协议、嵌套与边界检查见 [PROFILE_MONITOR](MLKEM512_PROFILE_MONITOR.md)。

## 数据解释约定

| 分类 | 含义与边界 |
|---|---|
| `keccak_permutation` | Keccak-f[1600] 置换；portable x4 路径中的四次标量置换也在此统计 |
| `sha_sponge` | SHAKE/SHA3 的吸收、填充、输出等独占开销，不重复包含 Keccak |
| `rejection_sampling` | 公共矩阵系数的拒绝采样；不同种子可能触发不同次数的 XOF 输出调用 |
| `noise_cbd` / `noise_control` | CBD 噪声采样及其外围控制；CBD 本身不采用拒绝采样 |
| `ntt` / `intt` / `basemul_acc` / `mulcache` | 各自算法范围，包含范围内部的标量模约减；BaseMul 与累加在软件中融合 |
| `explicit_reduce_convert` | 显式多项式约减与 Montgomery 转换，不代表所有模约减成本 |
| `compression` / `decompression` / `encoding` | 压缩、解压和系数/消息编码转换；未把量化与位打包强行拆分 |
| `zeroize` / `memory_copy` | 软件清零和 memcpy；不是 CPU—加速器数据搬运 |
| `api_control` / `kpke_control` / `matrix_control` / `unclassified` | 对应上层函数剩余工作及外层测量/分派开销，不遗漏于总周期之外 |

种子形式 Decaps 包含私钥展开 KeyGen，单独报告。Key-check 也单列，不用混合所有操作的平均耗时代表一次 KEM。官方记录各执行一次，其周期分布表示输入差异，不是重复计时抖动；公开向量通过也不等于正式认证。

本实验尚未接入 PQC 加速器，因此不能从 KAT 输入/输出字节数推断加速器传输量，不能从软件阶段占比直接得出真实硬件加速比。后续要分别测硬件核心、软件调用与搬运、完整 KEM API。

## 重现与断点续跑

在仓库根目录的 PowerShell 中，首次生成插桩副本和镜像：

```powershell
python scripts/mlkem512_profile/build.py
python scripts/mlkem512_profile/run.py --max-batches 1 --workers 1
python scripts/mlkem512_profile/collect.py --partial
```

首批检查通过后完成剩余批次并严格汇总：

```powershell
python scripts/mlkem512_profile/run.py --workers 6
python scripts/mlkem512_profile/collect.py
```

共 19 个批次，每批最多 8 条；批次仅在最终 PASS、输出、嵌套周期、工程参数、实际加载文件和来源哈希全部核验后写入 `success.json`。再次执行 `run.py` 会复核并跳过成功批次。已保存部分行但尚未成功的批次需要从该批开头重跑。

需要暂停时创建停止文件，脚本不再派发新批次，已经运行的批次完成后退出：

```powershell
New-Item -ItemType File -Path build/mlkem512_profile/STOP -Force
```

恢复时只删除该停止文件，然后续跑；已有通过结果下无需重建固件：

```powershell
Remove-Item -LiteralPath build/mlkem512_profile/STOP
python scripts/mlkem512_profile/run.py --workers 6
```

运行中不修改固件、TB 或运行脚本。已有结果会绑定这些输入的哈希；代码变更应建立新的实验结果目录，不能悄悄混合。

## 结果文件

目录：[results/official_baseline/mlkem512/profile](../results/official_baseline/mlkem512/profile/)。

| 文件 | 用途 |
|---|---|
| `summary.md` / `summary.json` | 各 API 独占占比、函数包含子调用的周期、相对正式基线的偏差及来源 |
| `cases.csv` | 每条官方记录的 API 周期、M 指令、栈和基线对照 |
| `phases.csv` | 每条记录的函数周期、调用次数 |
| `phase_map.json` / `build_manifest.json` | 事件定义、编译与镜像来源 |
| `batches/*/simulate.log` | 真正执行的仿真日志，每批有独立最终 PASS |
| `batches/*/project.xpr` | 当次工程配置快照；本机可运行工程在 `build/mlkem512_profile/batches/`，可由 `run.tcl` 重建 |

离线重新核验结果、不运行仿真或改写报告：

```powershell
python scripts/mlkem512_profile/collect.py --check
```

## 测量结论

145 条官方记录均逐字节匹配预期输出与返回值；每条的独占周期之和严格等于 API
`rdcycle` 差值，进入/退出事件配对且无越界。19 个批次各有独立最终 PASS，
原始索引 0..144 恰好各出现一次。共检查 148,160 B 输入、101,760 B 输出，
归档 6,235 条映射后的阶段记录（43 个阶段含未分类项 × 145 条）。

### 主要 API 的耗时组成

下表为各类 API 汇总周期的独占占比；同一行相加为 100%（显示值有舍入）。
“多项式算术”包括 NTT、INTT、BaseMul 累加、mulcache、显式约减/转换、加减六类，
不包含压缩和编码；函数内部的约减已经计入对应函数，未重复相加。

| API | N | Keccak 置换 | SHAKE/SHA3 外围 | 多项式算术 | 其他 |
|---|---:|---:|---:|---:|---:|
| KeyGen | 25 | 80.69% | 0.95% | 13.08% | 5.28% |
| Encaps | 50 | 72.96% | 0.92% | 19.13% | 6.99% |
| Decaps，展开私钥 | 20 | 71.36% | 0.89% | 21.38% | 6.37% |
| Decaps，含种子展开 | 10 | 75.24% | 0.92% | 17.91% | 5.93% |

多项式算术中，KeyGen 的 NTT 占整个 API 7.77%；Encaps、展开私钥 Decaps 的
INTT 分别占 9.52%、10.21%。缓存 BaseMul 累加本身分别占 KeyGen/Encaps/Decaps
的 1.30%/1.84%/1.98%。因此，增加乘法 PE 的收益需要放在完整 KEM 耗时中评价。

公钥检查的显式约减约占 51.06%–51.07%，私钥检查的 Keccak 约占 98.65%；
有效/无效返回均单列于 [原始汇总表](../results/official_baseline/mlkem512/profile/summary.md)。

分阶段记录也解释了部分输入间差异：25 条 KeyGen 中有 3 条、50 条 Encaps 中有
4 条调用了第二次 `shake128x4_squeezeblocks`，Keccak 次数分别由 27 增至 31、
26 增至 30。对应原始索引为 KeyGen 的 13/26/30 和 Encaps 的 38/41/43/82。
源码中首次 x4 调用每路输出三个块，补充调用每路输出一个块，因此“多一次调用”
代表四路共新增四次标量置换，不能把调用次数当作输出块数。

### 与正式基线的偏差

| API | 未插桩平均周期 | 插桩平均周期 | 周期增幅 |
|---|---:|---:|---:|
| KeyGen | 5,269,403.96 | 5,276,375.08 | +0.132% |
| Encaps | 5,581,096.62 | 5,589,453.98 | +0.150% |
| Decaps，展开私钥 | 6,937,739.25 | 6,947,834.25 | +0.146% |
| Decaps，含种子展开 | 12,132,085.40 | 12,149,071.40 | +0.140% |

全部记录的算法区间累计由 692,273,249 增至 693,266,495 周期，差值 993,246
（+0.1435%）；该累计仅用于核对插桩扰动，不代表某种应用的操作比例。
逐例扰动为 +0.0933% 至 +0.4568%，最高比例出现在短的公钥检查。
145 条记录各自的八类 M 指令计数均与原基线一致，总 M 为 3,486,720。

| 内存指标 | 正式 RV32IM 基线 | 独立 profiling 固件 |
|---|---:|---:|
| 有效镜像 | 26,272 B | 31,456 B |
| 静态区结束地址（十进制） | 31,940 | 37,128 |
| 预留 RAM / 栈 | 64 KiB / 16 KiB | 64 KiB / 16 KiB |
| 最大观测算法栈 | 12,928 B | 13,264 B |

正式镜像与数据保持原哈希；后续报告的真实加速比以未插桩的软件/硬件完整 API
另行对照。以上观测栈仍不是所有输入的最坏情况证明。

### 对加速范围的约束

若保持其他阶段不变，乐观地把上述六类多项式算术全部变成零周期，并假设没有
搬运和同步成本，按 `S = 1 / (1 - p)` 得到：

| API | 多项式占比 p | 该假设下的整 API 理想加速比 |
|---|---:|---:|
| KeyGen | 13.08% | 1.151× |
| Encaps | 19.13% | 1.237× |
| Decaps，展开私钥 | 21.38% | 1.272× |
| Decaps，含种子展开 | 17.91% | 1.218× |

这是基于插桩占比的设计估算，不是已测硬件收益或所有架构的绝对上限。
现有核只覆盖其中部分工作，真实接口还存在搬运、等待、格式转换成本；
若同时改变哈希实现、存储或软件调度，则需要重新测量，不能沿用此假设。

**工程方向因此应同时评估 Keccak/SHAKE 与多项式路径。** 先用已有多项式核建立
正确、可比的软硬件完整流程，再把 Keccak 加速作为独立增量，比较“软件、
仅多项式、仅 Keccak、两者协同”的完整 API 周期及 LUT/FF/DSP/BRAM 成本。
后续 PE 扩展与存储优化应根据这些端到端结果取舍。

## 下一步接入前需要解决的接口问题

主线固定为 **RV32IM 快速乘法＋软件** 对 **相同 CPU＋PQC 硬件**。RV32I 和迭代乘法保留为后续消融组；已有三组软件基线继续保留。下一步先建立软件/硬件接口契约和分阶段正确性对照，再修改计算核。

| 问题 | 现有实现 | 接入前的验收内容 |
|---|---|---|
| 运算域 | [HLS 顶层](../hls/src/mlkem_poly_mul256_v39e_true_one_dsp.cpp) 固定执行两次正 NTT、BaseMul、逆 NTT 和缩放；标准库的公共矩阵直接生成在 NTT 域，KeyGen 也需要保留 NTT 域结果 | 明确独立 NTT、INTT、NTT 域乘加命令；不能把已有 NTT 域数据送入完整乘法后再次变换 |
| 向量与复用 | [标准库 BaseMul](../third_party/mlkem-native/mlkem/src/poly_k.c) 执行 K=2 向量点积、32 位累加并使用可复用 mulcache；旧核只算一对多项式 | 定义缓存、累加、输出约减与存储驻留边界，先比较正确性再评估是否融合命令 |
| 数值表示 | 标准库使用带符号系数、Montgomery 缩放及懒约减；旧核有自己的 K²-RED、12 位打包与中间排列 | 逐阶段核对系数顺序、模 q 等价、缩放因子、输入界限；完整卷积通过不能代替这些检查 |
| 搬运与并行 | [AXI 包装](../rtl/axi/mlkem_polymul_axi_wrapper.v) 仅有 start/status/cycles 和三个 512 B 数据区；忙时不能同时写输入 | 首先量化一次调用的实际写入、等待、读回；根据实测决定批量接口、BRAM 常驻或双缓冲 |
| 存储容量 | 旧加速系统的程序 RAM 为 4 KiB，官方 KEM 软件基线为 64 KiB | 在相同 64 KiB CPU 环境接入，保持计时和数据布局可比，并重新实现测资源/时序 |

对接顺序：导出标准软件的真实中间操作数 → 阶段级 oracle → 接口/缩放适配 → 512 完整官方回归 → 未插桩完整 API 加速比 → 同约束资源与时序。硬件中的秘密数据也要纳入清零边界，保持软件基线包含清零的口径。

Keccak 是可独立评估的另一条加速路径。最直接的边界是 [Keccak 置换](../third_party/mlkem-native/mlkem/src/fips202/keccakf1600.c) 的 200 B 状态，但每次搬入搬出合计 400 B；需要比较单次置换接口与将 sponge 状态保留在硬件中的 SHAKE/SHA3 接口，纳入吸收、填充、输出、同步和清零成本。先根据全量阶段占比安排优先级，不能只比较裸置换周期。
