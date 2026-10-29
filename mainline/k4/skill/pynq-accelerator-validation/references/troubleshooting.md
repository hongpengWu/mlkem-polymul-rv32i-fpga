# 定位清单、提炼依据与边界

| 触发条件 | 定位步骤 | 报告处理 |
|---|---|---|
| 离线示例被声明为 board-live | 比较 plan、module.MEASUREMENT_KIND 与 session.describe 的类型标签 | 失败，不能以软件模拟充当实测 |
| 仅第一轮正确、后续失配 | 检查 reset/完成状态清理、输入是否被就地修改、回读缓冲是否刷新 | 保留首个失配，不混入正常统计 |
| 值数量正确但顺序错 | 检查 dtype、端序、字节/字偏移、符号扩展、输出长度和 stride | 指出首个失配路径及实际/黄金值 |
| 改黄金值后测试仍过 | 核对适配器是否返回固定值或复用了黄金代码；检查 plan 哈希 | 换独立来源黄金值，构造反例验证失败路径 |
| timeout 不生效 | 检查驱动是否无限 wait、单次 MMIO 读是否阻塞；外层时间只能在函数返回后检查 | 实现驱动内超时或独立进程/平台看门狗；不宣称线程能安全终止 DMA |
| 硬件结果偶发为旧数据 | 检查完整输入写入/缓存同步、完成先后关系、读回区域、前一事务是否仍在运行 | 先修正确性，不用增加重复次数掩盖 |
| 硬件周期明显小于主机时间 | 查看 cycle_scope、PS 传输、轮询间隔、驱动内部验证与报告落盘范围 | 分列硬件秒和墙钟秒，不混算加速比 |
| 综合时钟很高，板上却不达预期 | 查看 estimate 与 routed timing、运行时实际时钟及频率寄存器 | 不从 HLS EstimatedClockPeriod 宣称板上 Fmax |
| 资源数据为 N/A、报表缺失 | 核对工具版本、报告种类、stage 与 scope，检查解析器支持范围 | 失败或缺失，绝不转成0 |
| session.close 失败 | 检查通道是否仍活动，驱动释放/复位顺序是否有误 | 整轮失败，保留 close_error 后按平台流程恢复 |

## 从本队开发过程提炼

1. `mainline/k4/pynq/mlkem1024.py::run_case` 已实现输出头、长度、返回码、逐字节黄金结果和硬件计数器核对，并在失败时保存诊断、复位。提炼为通用适配器协议与首错退出规则，算法字段移入 `expected`。
2. 同文件 `run_repetitions/run_paired`、`results/k4/paired_firmware/board_20261023/summary.md` 将 API rdcycle、PS case wall、batch wall、固件下载分开。新工具保留独立时间口径，不自动混算加速比。
3. `mainline/k4/hls/scripts/collect_reports.py::synthesis_metrics/cosim_metrics` 把 HLS 综合估计与 COSIM 实测区分，明确不能把综合 worst-case 当 COSIM 总周期。新工具据此要求资源阶段与作用域，不把 HLS 数据标成板上测量。
4. 新增独立的饱和向量加法例子，验证无需 ML-KEM 向量、RV32 固件或本队寄存器即可运行工具。模拟身份、错黄金值、资源未知值等是本次故障注入覆盖的情形，并非虚构已发生的硬件故障史。

## 验证边界

本次 PC 验证证明运行器和已覆盖的接口防护可执行，不能证明别的算法或板卡性能。既有项目板上145用例与重复/恢复证据是该项目原驱动的历史记录；本次新适配器未重新做板卡实测，必须按实际环境运行并留存新报告。

工具支持 Python 可调用的单次顺序事务；GPU-only、纯裸机、分布式吞吐、视频异步流水、动态精度、随机输出/近似等价关系需要扩展适配器与比较器。对于大型张量，JSON 和逐项比较会有内存成本，可增加分块文件格式；不要直接用于超大视频帧/无限流。DMA 用户可以在自己的 run 中封装 allocate、flush/sync_to_device、recv-first 调度、bounded wait、invalidate/sync_from_device 和 finally 释放，但应依据具体 DMA/驱动版本验证 TLAST、缓存与错误位。项目真实主线是 MMIO，本提交不宣称已经验证通用 DMA 搬运封装。
