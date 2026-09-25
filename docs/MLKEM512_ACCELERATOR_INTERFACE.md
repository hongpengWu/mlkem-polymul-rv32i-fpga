# ML-KEM-512 软件/硬件接口契约

更新时间：2026-09-25。本文是标准库接入加速器前的接口审计和约定草案。
旧 HLS 核只作为历史基线保留；新 HLS 从标准库实际调用边界重新定义，不修改 CPU、标准算法、旧 HLS C++ 或已有 RTL。

## 为什么现在要做接口对齐

CPU baseline 和 HLS 独立测试分别证明了两件事：标准软件能正确完成 ML-KEM-512，
现有 HLS 核能正确完成一对普通多项式的负循环卷积。完整系统还要证明第三件事：
软件送入硬件的数据和硬件返回的软件数据处于同一个数学表示和调用边界。

如果这一步省略，最容易出现三类错误：

1. 标准库已经在 NTT 域的数据再次送入会自动执行 NTT 的完整乘法核，造成重复变换；
2. Montgomery 因子或逆 NTT 缩放位置不同，结果模 q 看似接近但后续打包结果错误；
3. 标准库一次计算 K=2 的向量点积，而旧核只接收一对多项式，软件端累加和数据搬运会改变计时口径。

这不是额外的形式工作，而是把“CPU 如何调用 PL、PL 返回什么”写成可验证的软硬件接口。

## 当前 AXI 包装的事实接口

事实来源为 [mlkem_polymul_axi_wrapper.v](../rtl/axi/mlkem_polymul_axi_wrapper.v)。
机器可读审计结果保存在 [current_contract.json](../results/accelerator_interface/current_contract.json)，
可由下面的命令重新生成：

```powershell
python scripts/mlkem512_interface/audit.py
```

| 地址 | 读/写 | 含义 |
|---:|---|---|
| `0x0000` | R/W | 控制；写 bit0 启动，写 bit1 清 done，写 bit2 清 access error；读 bit1 done、bit2 idle、bit3 busy、bit4 access error |
| `0x0004` | R | 硬件 busy 期间递增的周期计数 |
| `0x0008` | R | 固定 ID `V39E` |
| `0x1000..0x11ff` | W/R | A 存储区，256 个 16 位系数，两个系数打包到一个 32 位字 |
| `0x1200..0x13ff` | W/R | B 存储区，布局同 A |
| `0x1400..0x15ff` | R | 输出存储区，256 个 16 位系数，布局同 A |

启动前 CPU 写入 A/B；busy 期间 HLS 占用输入 RAM，新的输入写入会置 access error，
输出读取等待完成。复位后包装器逐项清空三个 RAM。一次完整调用的可比计时边界应明确包含：
输入写入、控制写入、等待 done、输出读取和必要的软件清零；不能只报告 HLS 内部周期。

## 标准库的实际数学接口

标准库事实来源为 `third_party/mlkem-native/mlkem/src/` 下的 `indcpa.c`、`poly.c`、
`poly_k.c`、`poly.h` 和 `poly_k.h`。

| 项目 | 标准库约定 |
|---|---|
| 参数 | ML-KEM-512，`K=2`，`N=256`，`q=3329` |
| 矩阵 | `gen_matrix()` 直接生成 NTT 域矩阵；可能经过自定义顺序排列 |
| 向量 | `polyvec_ntt()` 后作为 NTT 域输入参与矩阵向量乘法 |
| BaseMul | 对 K=2 的两个多项式对做向量点积和累加，每个输出系数对最后做 Montgomery reduction |
| mulcache | 第二个向量的每个多项式有 128 个缓存系数，缓存由 `polyvec_mulcache_compute()` 产生 |
| 系数 | 中间值采用 signed `int16_t` 和懒约减界限，不保证每个阶段都是 `[0,q)` |
| Montgomery | `R=2^16`，`QINV=62209`；`poly_tomont` 使用 1353，`invntt_tomont` 入口缩放使用 1441 |
| 主要调用顺序 | KeyGen：NTT → mulcache → 矩阵向量 BaseMul → `polyvec_tomont`；Encaps：NTT → mulcache → 矩阵向量 BaseMul → inverse NTT；Decaps：NTT(ciphertext vector) → mulcache → BaseMul → inverse NTT |

标准库的 `mlk_polyvec_basemul_acc_montgomery_cached()` 是当前最重要的接入边界。
它不是普通时域多项式乘法：输入已经在 NTT 域，第二个输入还带有可复用的 mulcache。

## 当前旧 HLS 核与标准库的差异

| 对比项 | 现有 HLS 顶层 | 标准库接入需求 | 结论 |
|---|---|---|---|
| 顶层操作 | 完整 FNTT(A) + FNTT(B) + BaseMul + INTT + scale | NTT 域向量 BaseMul/累加，结果通常继续留在 NTT 域 | 不能直接替换 |
| 输入域 | 普通系数多项式 | NTT 域矩阵、NTT 域向量、mulcache | 需要适配或拆分阶段 |
| 输出域 | 完整时域结果，内部用 1441 scale | 依据调用点可能需要 NTT 域结果或 inverse NTT 结果 | 必须逐阶段定义 |
| 累加 | 一次一对多项式 | `K=2` 向量点积，缓存复用 | 需要硬件累加或明确 CPU 累加边界 |
| 表示 | 顶层 signed 16 bit，内部 unsigned 12 bit，输出 canonical | signed lazy coefficients，模约减位置由标准库约定 | 需要范围/缩放 oracle |
| 存储 | 三个 512 B bank，busy 时不可写 | 多个 NTT 多项式、mulcache 和向量结果驻留 | 需要批量命令或 BRAM 常驻设计 |

因此，旧核的独立 HLS 通过记录不能直接作为标准库 BaseMul 的通过证据。
机器清单明确标记 `direct_drop_in=false`，避免后续误接。旧核位于 `hls/src/`，
继续作为历史基线和完整时域多项式乘法对照；新的标准接口实现位于
[`hls/mlkem512_basemul_k2/`](../hls/mlkem512_basemul_k2/)。

## 新 HLS 第一版边界

新设计的顶层为
`mlkem512_basemul_acc_k2(const int16_t a[2][256], const int16_t b[2][256],
const int16_t b_cache[2][128], int16_t result[256])`。它只完成标准库
`mlk_polyvec_basemul_acc_montgomery_cached()` 的 K=2 向量点积，不执行 NTT、
逆 NTT、压缩、解压或 1441 缩放。

| 输入/输出 | 布局 | 语义 |
|---|---|---|
| `a[k][n]` | `k=0..1, n=0..255` | NTT 域矩阵行，当前标准库约束为 `[0,4095]` |
| `b[k][n]` | `k=0..1, n=0..255` | NTT 域向量，允许 signed lazy `int16_t` 表示 |
| `b_cache[k][i]` | `k=0..1, i=0..127` | `b` 的 mulcache，缓存 `b[4i+1]·ζ[64+i]` 和 `b[4i+3]·(-ζ[64+i])` |
| `result[n]` | `n=0..255` | K=2 累加后逐系数 Montgomery reduction 的 NTT 域多项式 |

第一版在 HLS 中展开 K=2 累加并以一组系数对为流水粒度，便于先获得可解释的
延迟和资源基线。`b_cache` 保持为独立输入，是为了匹配标准库的复用语义；后续
可以在同一接口审计基础上增加“硬件内部生成 cache”的融合变体，不能把两者的计时口径混在一起。

### Vitis HLS 2024.2 验证结果

新顶层已经在 `xc7z020-clg400-1` 上用 10 ns 时钟完成 C 仿真和 HLS 综合：
103/103 个 testbench 用例通过，流水线 II=1，估算核延迟 137 cycles，估算 Fmax
150.83 MHz；HLS 资源估算为 DSP 12、LUT 310、FF 599、BRAM 0。生成接口为
`ap_ctrl_hs` 加数组 `ap_memory` 端口，适合后续用 BRAM/AXI 适配层接入。
这些是 HLS 阶段估算，完整 Vivado 工程的综合、布局布线和时序结果仍需单独测量。
报告和导出 IP 见 [`results/accelerator_interface/hls_synthesis/`](../results/accelerator_interface/hls_synthesis/)
和 [`hls/mlkem512_basemul_k2/ip/`](../hls/mlkem512_basemul_k2/ip/)。

## 本阶段已经完成

- 核对 AXI 寄存器、存储窗口、控制位、busy 访问规则和周期计数器。
- 核对 HLS 顶层签名、内部 FNTT/BaseMul/INTT/scale 四类阶段、`q=3329` 和 1441 缩放表达式。
- 核对标准库的 NTT 域矩阵、NTT 域向量、K=2 累加、mulcache、Montgomery `R=2^16`、1353/1441 因子。
- 生成带源文件 SHA-256 的 [current_contract.json](../results/accelerator_interface/current_contract.json)。
- 通过 `collect.py --check`、`verify_sources.ps1`、Markdown 链接检查和 `git diff --check`。

## 下一步实施顺序

1. **阶段 oracle**：在不改变正式 ML-KEM 驱动的前提下，建立 NTT、mulcache、K=2 BaseMul、inverse NTT 的输入/输出向量格式；每个向量同时保存 signed 表示、canonical mod-q 表示、缩放说明和系数顺序。
2. **软件参考调用**：从 portable C 的实际函数边界导出一组代表性中间值，并用独立 Python/C oracle 检查 Montgomery 因子、范围和排列；不能只比较最终 KEM 输出。
3. **最小硬件边界**：已选定 NTT 域 BaseMul 累加作为第一版目标；旧完整乘法核保留为独立对照，新 HLS 从标准接口重新实现。
4. **仿真接入**：先用少量官方 512 记录跑 CPU＋PL 的阶段结果，再扩大到 145 条；任何结果不一致先定位域、缩放、布局或传输边界。
5. **公平测量**：使用未插桩 RV32IM-fast 软件基线，端到端计时包含输入写入、启动、等待、输出读取和软件清零；硬件内部周期另列。
6. **实现与扩展**：接口正确后再做 64 KiB Vivado 实现、资源/时序、Keccak 对照和后续 PE/BRAM 优化。

本阶段不修改 `third_party/`、`hls/src/`、`rtl/accelerator/`、`rtl/axi/` 或正式 baseline 固件。
