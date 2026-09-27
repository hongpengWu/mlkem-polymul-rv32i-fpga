# ML-KEM-1024 Keccak/SHAKE HLS

K4 主线的独立、逐位精确 FIPS 202 运算核。支持 SHAKE128/256、SHA3-256/512。
目前完成独立 HLS 验证，完整 K4 CPU 加速系统及其官方 KAT 待接入。

## 目录与运行

- `src/`：核心和接口；`tb/`：独立差分向量及测试。
- `scripts/`：向量生成和证据校验；`run_hls.tcl`：统一入口。
- 精选测量见 [结果](../../results/hls/mlkem1024_keccak/summary.md)。

工具：`E:/Xilinx/Vitis_HLS/2024.2/bin/vitis_hls.bat`；目标 `xc7z020-clg400-1`；
10 ns 时钟、10% uncertainty、最多 8 线程。
默认生成目录 `E:/hls/k4_io1/<时间戳_PID>/`，使用短路径，工程/IP/缓存不入 Git。

```powershell
& 'E:/Xilinx/Vitis_HLS/2024.2/bin/vitis_hls.bat' -f E:/pqc/mlkem-polymul-rv32i-fpga/hls/mlkem1024_keccak/run_hls.tcl
```

沿用用户提供的顶部 0/1 开关范式：

| 开关 | 默认 | 功能 |
|---|---:|---|
| CSIM | 1 | C 仿真 |
| CSYNTH | 1 | HLS 综合 |
| COSIM | 1 | Verilog 协同仿真 |
| VIVADO_SYN | 0 | 导出时运行 Vivado 综合 |
| VIVADO_IMPL | 0 | 导出时布局布线，优先于 SYN |
| EXPORT | 0 | 显式导出 IP；VIVADO_SYN/IMPL 需要置 1 |
| IO_OPT | 1 | 0 字节访存基线；1 打包访存优化 |

开关均可用同名 `HLS_` 环境变量覆盖；`HLS_BUILD_ROOT` 设置短构建根目录，
`HLS_RUN_ID` 设置运行名。新综合必须使用新目录，不 reset 旧目录。
只补 COSIM/EXPORT 时设置 `HLS_CSYNTH=0` 和已成功综合的 `HLS_RUN_ID`，
源码、TB 和配置必须匹配。每次冻结输入并保存哈希；运行锁禁止重复占用。
例如新建完整运行并做布局布线，先设置 `$env:HLS_EXPORT='1'`、
`$env:HLS_VIVADO_IMPL='1'` 再执行上述命令。

运行结果在外部目录 `reports/metrics.json`；失败返回非零。综合延迟估计与
RTL 实测总周期分别记录，不使用综合 worst-case 冒充 TotalExecution。

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
python hls/mlkem1024_keccak/scripts/generate_vectors.py --check
python hls/mlkem1024_keccak/scripts/collect_reports.py collect --run-dir E:/hls/k4_io1/opt02 --strict
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
