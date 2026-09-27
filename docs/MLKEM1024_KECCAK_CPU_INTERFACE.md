# K4 Keccak CPU 接口与移植断点

2026-09-27：已完成实际 RV32IM-fast CPU＋Keccak 的 RTL 组件闭环，并通过标准库的
custom FIPS202 provider 接入完整 K4 API。官方系统RTL KAT已145/145通过；K2 和 CPU-only 基线保持冻结。

代表性官方RTL用例原索引0、1、115已3/3通过，覆盖KeyGen、Encaps、带SHAKE续取的
隐式拒绝Decaps；真实HLS启动/完成85次（81 HASH＋4 SQUEEZE）。同配置CPU基线对照为
4.180× / 3.621× / 3.668×；这是最先完成的代表用例历史数据。
后续19批已145/145通过：全量KeyGen/Encaps/Decaps为4.203×/3.636×/3.602×，
测试集API总周期比3.8028×，3,188次HLS调用（含68次续取）均有真实RTL证据。
首批墙钟185.4 s，包含Vivado编译/展开和RTL运行；这与芯片执行时间不同。
详见[逐例原始证据与汇总](../results/keccak_cpu/kat/summary.md)。

## 已验证内容

- [主机调用统计](../results/keccak_cpu/call_profile/README.md)：145/145 条官方 K4 输入的
  输出/返回值一致；8,683 次标量 Keccak 置换。此结果是主机调用次数，不是 CPU 阶段周期。
- [CPU 硬件闭环](../results/keccak_cpu/smoke/README.md)：10 次调用、216 个结果字、
  10 次真实 HLS 启动/完成，四种模式、上下文交错、续取及错误返回全部通过。
- 首版接口按32-bit打包搬运；每次恢复和保存208B上下文。没有DMA、零拷贝或完整KEM加速比声明。
- 新系统RTL默认128KiB程序RAM，固件预留32KiB栈；CPU+存储+桥+Keccak的OOC布局布线已完成，资源足够，100 MHz内部setup −1.367 ns待优化。

## 地址及协议

新窗口 `0x50010000–0x50013fff`，与旧K2窗口独立。以下均为相对偏移。

| 偏移 | 内容 |
|---|---|
| 0x0000 | HLS启动/状态；禁止auto_restart和busy期间再次启动 |
| 0x0004 / 0x0008 / 0x000c | GIE / IER / ISR；ISR为toggle-on-write |
| 0x0010 | 有符号返回值，0成功、-1参数错误、-2上下文错误 |
| 0x0018 / 0x0020 | 输入/输出字节数 |
| 0x0028 / 0x0030 | 模式0–3 / HASH=0、SQUEEZE=1、CLEAR=2 |
| 0x0100 / 0x0104 | 累计启动数 / 启动写握手至观测完成的busy周期 |
| 0x0108 / 0x010c | CPU缓冲写/读事务数，包含上下文 |
| 0x0110 | bit0 busy、bit1 done、bit2 error；后两位W1C |
| 0x1000–0x17ff | 2048B输入，32-bit little-endian |
| 0x2000–0x2fff | 4096B输出，32-bit little-endian |
| 0x3000–0x30cf | 26×64-bit上下文，CPU通过52个32-bit word访问 |

CPU AXI AW/W独立接收，读写串行；控制桥等待HLS响应才接受下一事务。
数据RAM在CPU和HLS之间按busy状态分配所有权；busy期间CPU缓冲访问不改存储并置错。
未对齐/无效地址置错；reset不清除BRAM内容，调用方必须初始化输入和上下文。
驱动启用done中断以独立计量busy；轮询ISR，只有确认pending才写1清除，避免误置中断。
超时和驱动参数错误返回-3/-4；超时后禁止继续复用状态，应重置系统并排查。

CLEAR的HLS流水线在退出条件上生成地址0xd0、EN=1、WEN=0的无用读探测。
adapter只丢弃这一确切的CLEAR退出探测，不访问RAM；其他越界仍置错，写边界保持26 words。

## 标准库接入与系统验证

实测调用形状均在现有HLS容量内：SHA3-256 1568→32、SHA3-512 33/64→64、
SHAKE256 33→128和1600→32、SHAKE128每lane 34→504，必要时续取168。
17次x4续取分布在16条官方记录，不能忽略；观察到最长672B不代表所有种子的上界。

1. 已在独立加速构建中包装FIPS202接口，保持第三方源码和正式软件基线不变。
   SHA3/SHAKE256走HASH；合并SHAKE128吸收和首次输出为HASH(34,504)。
2. 已为标准库x4的四条独立流分别保存四个HLS上下文，续取恢复原lane。
   标准库25-lane状态和HLS26-word状态含义不同，不能直接强制转换；需独立上下文适配。
3. 已完成代表用例及145条可恢复加速RTL回归，逐字节官方输出、返回值和硬件调用计数均通过。
4. 已与同CPU、同128/32KiB配置的未插桩K4软件基线对比完整API周期；
   计入打包、搬运、上下文、命令与等待开销，再决定是否保留状态于硬件、添加多context槽或DMA。
5. 完整系统OOC已完成；优先优化程序RAM写控制与adapter ready组合反馈以收敛100 MHz，再完成板级时钟/复位及烧录产物，实板最后。

组件构建入口为 `scripts/mlkem1024_keccak/build_smoke.py` 和 `run_smoke.py`；
完整系统使用 `build_kat.py`、`run_kat.py` 和 `collect_kat.py`。
固件镜像17,824 B，静态占用36,676 B；与CPU-only一致使用128 KiB RAM / 32 KiB栈。
构建检查全部FIPS202符号来自硬件provider，不链接软件Keccak，也无软件回退。
provider共享6 KiB打包缓冲，非可重入；SHAKE128拥有34 B输入副本并保留任意次数的块续取，
单条命令最多4096 B输出。CPU中间量清零计入API周期；加速器BRAM擦除尚待实现和验证。

运行方法：先 `python scripts/mlkem1024_keccak/run_kat.py` 验证原索引0、1、115，
再 `python scripts/mlkem1024_keccak/run_kat.py --remaining` 仅运行未通过的用例，每批最多8条。
当前已全量完成，无需重跑；只读验收使用`python scripts/mlkem1024_keccak/collect_kat.py`。
`python scripts/mlkem1024_keccak/collect_kat.py --partial --write` 汇总代表性结果；
全量成功后调度器自动运行不带`--partial`的严格汇总，必须145条唯一覆盖。
`build/keccak_cpu/kat_progress.json` 保存当前运行目录/断点；创建`build/keccak_cpu/STOP`
可在当前批结束后停止，恢复前移除该标记。运行中的冻结输入不能改动。
机器为Ryzen 7 6800H（8核16线程）；Vivado `general.maxThreads=8`，xelab使用auto。
RTL逐周期仿真不承诺8倍并行提速。本轮不重复独立HLS综合/实现。

HLS生成RTL只从外部已验证短路径复制到忽略的运行快照，核对哈希，不纳入Git。
定时任务 `pqc-kat` 已删除，后续由用户发起继续。
