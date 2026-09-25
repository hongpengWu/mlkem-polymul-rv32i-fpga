# ML-KEM-512 完整公开向量回归协议

本协议定义三种 PicoRV32 配置运行 ML-KEM-512 官方公开向量的方式。
结果记录在 `results/official_baseline/mlkem512/`；先前 `keygen512_tc1/` 保留为独立历史里程碑。

## 1. 向量范围与接口

来源是仓库固定的 ACVP-Server 提交，沿用 [来源清单](../vectors/official_kat/acvp/SOURCES.md)。
每个 CPU 配置运行 145 项，三配置共 435 次测试执行；这里的 435 次执行与主机端
三个参数集合计 435 项是不同统计口径。

| op | 操作 | 数量 | 软件输入 | TB 核对内容 |
|---|---|---:|---|---|
| 1 | KeyGen | 25 | d、z | ek 800 B、dk 1632 B，返回 0 |
| 2 | Encaps | 50 | ek、m | 密文 768 B、共享密钥 32 B，返回 0 |
| 3 | Decaps（展开密钥） | 20 | dk、密文 | 共享密钥 32 B，返回 0 |
| 4 | 种子展开＋Decaps | 10 | d、z、密文 | 共享密钥 32 B，返回 0 |
| 5 | Encapsulation Key Check | 20 | ek | 有效返回 0，无效返回 -4；各 10 项 |
| 6 | Decapsulation Key Check | 20 | dk | 有效返回 0，无效返回 -5；各 10 项 |

KeyGen 来自 FIPS203；其余分别来自 FIPS203 和 FIPS203-tr1，操作 4 只在后者出现。
用例身份保留 `dataset/revision/vsId/tgId/tcId/op`，不能仅凭重复出现的 tcId 区分用例。
首八项覆盖所有操作及两类密钥检查的成功/失败路径，之后保持剩余源用例顺序。

隐式拒绝的解封装仍返回 0，必须核对官方预期的拒绝密钥，不能把返回 0 当作密文有效。
本批 30 项解封装记录中，15 项预期密钥与 `J(z || c) = SHAKE256(z || c, 32 bytes)` 一致；
FIPS203 展开密钥、tr1 展开密钥和 tr1 种子密钥三组各 5 项，作为隐式拒绝覆盖单独登记。
已收录密钥检查用例均为规定长度；本回归不声称覆盖所有错误长度或所有可能输入。

## 2. 固件与存储

算法使用固定提交的 `third_party/mlkem-native/` 便携 C，原算法文件逐字节保持不变。
仅禁用随机 API；KeyGen、Encaps、Decaps、check_pk、check_sk 均链接进同一个通用程序。
沿用上游默认清零及编译屏障，不启用原生架构后端或 LTO。

两份固件均由 GCC 13.3.0、`-O3`、ILP32 和其余相同选项编译，只改变 `-march=rv32i/rv32im`。
迭代和快速配置共用 RV32IM 镜像，三组 CPU 参数分别为 `MUL/FAST_MUL/DIV=0/0/0、1/0/1、1/1/1`。

三组均复用原 `cpu_benchmark_system` 的 CPU/AXI/XPM RAM 路径，RAM 为 64 KiB，栈保留
`0xbff0..0xfff0` 共 16 KiB；链接器拒绝静态区与栈重叠。代码、静态数据、栈观测与
有效镜像大小单独统计。栈观测覆盖本批用例，不能作为所有输入的形式化上界。

145 项原始输入（或恢复时选取的未完成批次）由 TB 模拟的主机邮箱逐词提供，固件仅保存当前用例，不将整批向量
计入算法 RAM 需求。CPU 写 debug reg12 请求顺序索引，并以 reg15 的 `0x200` 提交请求；
TB 在下一下降沿向 reg10 写输入词、reg11 写应答序号，CPU 正常加载并组装输入缓冲区。
预期输出和预期返回码只存在于 TB，不能通过邮箱提供给 CPU。

这属于仿真输入设施，不是新增的板级主机接口。上板阶段需要另行提供实际输入通道
或片上测试数据；本回归不把邮箱视为已经实现的板级功能。

## 3. 计时与检查

每例输入准备后，CPU 回传实际输入缓冲区，TB 与官方数据逐字节比较。之后用两次
`rdcycle` 包围操作分派和对应完整 API 调用。输出串流和 TB 核对在区间外，默认算法清零在区间内；
空计时区间单独记录，不扣除。确定性种子由官方向量提供，因此没有计入熵源获取时间。

操作 4 在同一计时窗口内先由 `d || z` 生成展开密钥，再解封装，必须与操作 3 分开报告。
这里没有官方展开密钥 oracle，只通过最终共享密钥核对该路径；不声称中间 ek/dk 已被直接逐字节核对。
此通用驱动包含操作分派，与旧首例专用驱动的少量外围指令不同，不替换旧首例结果。

TB 从真实 CPU 执行边沿验证 rdcycle 差值，在该窗口统计八类 M 指令；同时检查：

- 每例身份、输入、输出、长度、事件顺序和完整数量；
- API 返回码与官方 testPassed 的映射；
- CPU trap、访问范围、栈界限和 16 字节对齐；
- 计时区间没有调试 MMIO 写入，CPU 不写主机邮箱寄存器；
- 本次仿真声明的全部用例、字节核对完成后才输出 `MLKEM512_PASS`；常规运行声明 145 项，
  恢复批次由 `EXPECTED_CASES` 声明实际批长，批次 PASS 不能单独代表全套通过。

按操作、数据集和密钥检查结果分别统计最小、平均、中位数、最大和 P95 周期；
不同操作及有效/无效密钥检查不得混成一个“完整 KEM 平均延迟”。
最终统计为每个向量保留一次通过验证的执行；中断后重跑的未完成批次不纳入重复样本。
分布描述的是这批输入之间的差异，不是实板重复运行的抖动。
时长按 100 MHz 仿真时钟换算，不代表新配置已完成布线后频率验证。

## 4. 复现

在仓库根目录运行：

```text
python scripts/mlkem512_suite/build.py
python scripts/mlkem512_suite/run.py
python scripts/mlkem512_suite/collect.py
```

`run.py` 默认并行启动三配置；使用 `--config rv32i`、`rv32im_iterative` 或 `rv32im_fast`
可单独运行。`build.py --tool-dir` 和 `run.py --vivado` 可指定本机工具位置。
常规长回归不记录波形，只保留逐例数据、完成标记和错误，减少无用仿真开销。
每配置启动前保存输入 SHA-256，结束后复核；生成的 `.xpr` 与镜像可供检查，缓存留在本地。

### 关机断点与分批恢复

2026-09-24 的 `checkpoint/` 保存了 RV32I／迭代 RV32IM／快速 RV32IM 分别
25／31／38 条完成记录，总计 94 条。每条 ROW 均为原 TB 完成输入、输出、返回码和
计时检查后打印；保存的三份原日志都没有最终 PASS。原前缀保持原样，续跑只选择
各配置剩余的 120／114／107 个官方身份，不将未完成用例当作通过。

恢复入口为：

```text
python scripts/mlkem512_suite/collect_resumed.py --check-checkpoint
python scripts/mlkem512_suite/resume.py --prepare-only
python scripts/mlkem512_suite/resume.py --workers 4
python scripts/mlkem512_suite/collect_resumed.py --archive-project-evidence
python scripts/mlkem512_suite/collect_resumed.py
```

恢复阶段不运行 `build.py` 或普通 `run.py`。校验器核对已保存 CSV 的 SHA-256、
CSV 与原日志完整 ROW 的逐行一致性及每个官方身份，再核对原输入快照。
CPU RTL、固件、构建清单和完整官方 fixture 必须与保存版本一致；原 TB 和脚本
快照仍保留，当前 TB 仅允许通过 `EXPECTED_CASES` 选择批长，逐例检查与计时边界不变。

默认批长为 8，形成 15／15／14 批，共 44 批。每批 `batch.json` 记录原始索引映射，
批内索引从 0 连续编号；输入及期望 `.mem` 逐词与官方记录重建结果核对。
批次结果位于 `batches/<config>/batch_<首索引>_<末索引>/`，包括冻结的
`run_inputs.json`、真实 `simulate.log` 和经验证的 `success.json`。
独立工程位于 `build/mlkem512_suite/batches/<config>/<batch>/`；
校验器同时核对 XPR 参数、仿真实际加载的镜像和 fixture。

完整校验成功批次后，`--archive-project-evidence` 将其 `.xpr` 原样归档为结果目录内的
`project.xpr`，并生成 `project_evidence.json`，绑定批次、运行输入、成功记录、日志、
XPR 及实际暂存文件的 SHA-256。最终汇总引用这些结果目录内的证据，不依赖被 Git 忽略的
`build/` 路径。本地工程仍存在时继续严格检查实际暂存文件；删除缓存后则必须由完整归档
通过相同的固件／fixture／日志哈希及 CPU／批长参数检查。归档 XPR 是来源证据，
常规可打开的主套件工程仍为 `vivado/mlkem512_<config>/mlkem512.xpr`。

`resume.py` 重启后复用已有分批方案，只有通过重新验证的成功批次才跳过。
默认并发为 4，本次确认内存余量后以 6 路完成；同一结果目录不得同时运行
两个恢复调度器。创建 `build/mlkem512_suite/STOP` 会停止启动新批次并等待当前批次
正常结束，删除 STOP 后即可继续。若强制结束进程，未完成批次的已打印 ROW 不会
自动成为新断点，下次重跑整个未完成批次；原始 checkpoint 与已验证成功批次保留。

恢复汇总必须满足每配置的原始 `case_index=0..144` 完整且唯一，
每配置输入／输出核对总数为 148,160／101,760 字节，两种 RV32IM 每个原始用例的
八类 M 指令计数完全一致。只有这些检查全部通过，`collect_resumed.py` 才输出
汇总文件；`--check` 执行同样检查但不改写结果，未完成阶段不能称为全套通过。

报告将原始已验证前缀与独立完成的续跑批次明确分开，不拼接或伪造单次 145 条 PASS。
关机前缀没有结束记录，因此其启动至结束的周期和全程 M 总数不可恢复；
配置级 `total_sim_cycles`、`all_m` 为 `null`，续跑批次全程总数另列且包含各批重复启动。
算法区间周期和 M 总计仍覆盖最终全部 145 条记录。配置栈值取原前缀算法区间与完整续跑
批次中的最大观测深度，分组表使用算法区间观测值；二者都不是最坏输入上界。

比较器的负向检查通过以下命令复现：

```text
vivado -mode batch -source scripts/mlkem512_suite/verify_rejection.tcl
```

脚本只在独立临时工程中翻转首例预期公钥的一个 bit。TB 应精确报错
`case=0 output=1 byte=0 got=28 expected=29`，外层脚本将该指定失败认定为
`MLKEM512_REJECTION_CHECK_PASS`；日志独立保存于 `negative_check/`。

结果属于官方公开向量的本地 CPU RTL 回归，不等于正式 CAVP 算法验证或 FIPS 140-3 模块认证。
768/1024、PQC 加速系统和实板各自需要独立验证。

2026-09-24 执行结果：三组各 145 / 145 条通过，44 个续跑批次全部归档；严格合并校验通过。统计见 [完整汇总](../results/official_baseline/mlkem512/summary.md)。
