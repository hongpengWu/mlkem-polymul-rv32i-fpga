# ML-KEM-1024 Keccak/SHAKE HLS

K4主线的逐位精确FIPS 202运算核，支持SHAKE128/256、SHA3-256/512。
核心集成与官方145条RTL验证已经完成；当前状态见
[项目进度](../../../docs/PROJECT_STATUS.md)。

## 运行入口

- `src/`：算法和接口；`tb/`：独立差分向量和测试；`scripts/`：数据与证据工具。
- [主流程](../flow.tcl)的HLS开关管理CSIM、CSYNTH、COSIM及IP导出。
- [主线复现说明](../README.md)说明环境变量和可选短构建目录。
- [历史结果](../../../results/hls/mlkem1024_keccak/summary.md)保存既有性能记录。

从仓库根目录配置工具环境并运行：

```powershell
$env:FLOW_HLS='1'
$env:FLOW_KAT_SUBSET='0'
$env:FLOW_COLLECT='0'
$env:FLOW_CHECK_ONLY='0'
tclsh mainline/k4/flow.tcl
```

默认CSIM/CSYNTH/COSIM开启。使用 `FLOW_SHORT_ROOT` 指定短构建区；实际生成文件不回写源码。
测试数据中的旧说明保持原始字节，便于核对历史输入哈希，当前命令以本页为准。
重用综合结果时需匹配源码、TB、配置和报告哈希，禁止覆盖既有运行。

## 接口

控制为 AXI-Lite，数据为 BRAM；输入/输出使用 little-endian uint32 打包。
具体错误语义见 [头文件](src/mlkem1024_keccak_accel.h)。

| 对象 | 约定 |
|---|---|
| input | 512 words / 2048 B；覆盖 K4 H(ek)=1568 B、J(z\|c)=1600 B |
| output | 1024 words / 4096 B 每次命令；SHAKE 可续取 |
| context | 26 个 uint64：25 lane + magic/mode/cursor |
| mode | 0 SHAKE128；1 SHAKE256；2 SHA3-256；3 SHA3-512 |
| command | 0 HASH（初始化/吸收/填充/输出）；1 SQUEEZE；2 CLEAR |

SHA3 输出固定 32/64 B，完成后清除 context。SHAKE 支持零输出、任意偏移续取和
交错 context，适用于矩阵拒绝采样的 504 B 初始输出及后续 168 B 块。
不支持未填充的增量吸收；大于 2048 B 的通用消息需要扩展接口。
无效调用不修改输出/context。末 word 高位清零、后续 word 不变。三个缓冲不可重叠。
context 由调用方隔离、保管、清除。周期依赖公开长度和模式，未完成系统侧信道评估。
BRAM 端口不代表 DMA/零拷贝已完成；CPU 仲裁、批量缓冲和驱动仍需设计及测量。

## 验证和优化

两种配置均通过 C 仿真及 Verilog 协同仿真：109 次事务，包括 74 个 HASH 向量、
分段 SHAKE、交错上下文、边界、清除、错误调用。独立 oracle 为 Python hashlib/OpenSSL。
这些是本地 FIPS 202 差分测试，**不是官方 ACVP KAT**；见 [TB 说明](tb/README.md)。

```powershell
python mainline/k4/hls/scripts/generate_vectors.py --check
python mainline/k4/hls/scripts/collect_reports.py collect --run-dir build/k4/hls_io/opt02 --strict
```

采用 25-lane 并行、单轮复用 24 轮；限制一个 permutation 实例，避免外层 pipeline
触发 24 轮全展开。IO_OPT=1 按 rate 块吸收打包 word，去掉变量取模，每步最多输出 4 B。

参考 [Prompt2A](https://github.com/hongpengWu/Prompt-Set-Design/blob/main/UKF_Prompt/Prompt2A.md)
和 [Prompt2B](https://github.com/hongpengWu/Prompt-Set-Design/blob/main/UKF_Prompt/Prompt2B.md)
的报告驱动方法：固定功能回归，每轮一个主要结构策略，对比周期、资源、时序。
Keccak 必须逐位精确，不做 UKF 的有损定点量化，也不截断 64-bit lane。
后续按证据优化控制位宽、banking、调度和复用。

接下来：K4 调用分布测量 → CPU/缓冲接口 → 代表性官方 KAT → 完整145条RTL回归 →
同条件端到端/系统实现 → 最后上板。核测试收益不等于完整 KEM 加速比，
HLS 时钟估计不等于布局布线时序或板级频率。

COSIM 周期包含生成驱动的 AXI-Lite 参数设置、状态轮询、返回寄存器读取。
驱动会跳过未改变的参数写入；相同长度事务的周期可能因前一事务配置而不同。
不将这些周期称为纯 permutation 周期，也不据此证明恒定时间。
