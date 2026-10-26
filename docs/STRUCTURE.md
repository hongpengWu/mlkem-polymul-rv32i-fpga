# 目录与复现导航

2026-10-26：发布分支为 `last`。K4 主线源码已集中到 `mainline/k4/`，
两个人工维护的 Tcl 入口为 `flow.tcl` 与 `bd_axi.tcl`。
完整运行说明见 [主线 README](../mainline/k4/README.md)。

```text
仓库/
├── mainline/k4/        当前K4源码、固件、TB、约束、Notebook和两个Tcl入口
├── results/            统一证据根目录；历史结果内容保持原样
├── release/            板上部署包
├── build/              不入Git的生成工程和中间文件
├── rtl/cpu/            共用PicoRV32
├── third_party/        固定版本ML-KEM C库
├── vectors/            固定官方测试数据
├── scripts/            共用工具、官方数据工具及历史CPU/K2流程
├── firmware/           共用启动代码、CPU-only/K2固件和历史镜像
├── hls/                历史K2源码与旧本地HLS生成目录
├── rtl/benchmark/      CPU-only存储与系统包装
├── rtl/accelerator/    历史K2硬件
├── tb/                 共用CPU/软件测试、历史K2测试
├── constraints/        历史K2约束
├── vivado/             历史CPU-only/K2工程
└── docs/               进度、构建、性能与历史说明
```

## 日常入口

| 工作 | 位置 |
|---|---|
| 看进度 | [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| HLS加速器算法与测试 | [mainline/k4/hls/](../mainline/k4/hls/) |
| CPU、存储、MMIO与AXI硬件 | [mainline/k4/rtl/](../mainline/k4/rtl/) |
| RISC-V上的C程序 | [mainline/k4/firmware/](../mainline/k4/firmware/) |
| 系统与AXI仿真 | [mainline/k4/tb/](../mainline/k4/tb/) |
| Jupyter演示源码 | [mainline/k4/pynq/](../mainline/k4/pynq/) |
| HLS、核心及独立PL流程 | [flow.tcl](../mainline/k4/flow.tcl) |
| BD、AXI和overlay流程 | [bd_axi.tcl](../mainline/k4/bd_axi.tcl) |
| 上板配套文件 | [release/mlkem1024_pynq/](../release/mlkem1024_pynq/) |
| 迁移映射与验证 | [results/reorganization/](../results/reorganization/) |

主线的 `scripts/` 是两个 Tcl 调用的 Python 辅助工具，承担编译、输入快照、
官方输出校验和证据归档；没有把这些必要检查删掉。
共用CPU、第三方库和官方数据通过仓库相对路径引用，不再复制一份。

## results/ 中保存什么

| 子目录 | 内容 |
|---|---|
| `official_reference/` | 主机端三种参数的官方参考验证 |
| `official_baseline/` | 512/768/1024的CPU-only官方验证 |
| `cpu_baseline/` | 早期多项式和不同CPU配置实验 |
| `accelerator_interface/` | 历史独立K2 HLS/MMIO/板级证据 |
| `accelerator_cpu/` | 历史CPU+K2 BaseMul结果 |
| `hls/mlkem1024_keccak/` | K4 HLS基线、优化和物理实现证据 |
| `keccak_cpu/` | K4核心、板级、PS–PL分阶段结果 |
| `reorganization/` | 新旧路径映射、文件一致性与迁移验证 |

K4当前全量核心证据在 `keccak_cpu/candidates/timing_decode_v3/kat/`；
已发布overlay证据在 `keccak_cpu/pynq/20261005_psaxi06/`。
日期和批次子目录记录具体运行，失败和中断不会被归并成PASS。
TB负责定义检查，日志和输入哈希负责证明某一版本实际运行过，两者不能互相替代。

## 构建路径与历史文件

从干净克隆开始，版本控制内的源码、测试输入和必要依赖均通过仓库相对位置定位。
K4的默认构建目录为 `build/k4/`，被 `.gitignore` 排除；需要绕过AMD工具的长路径限制时，
可用 `FLOW_SHORT_ROOT`、`HLS_BUILD_ROOT` 或 `BD_SHORT_ROOT` 指向仓库外的短目录。
这只改变生成物位置，不改变或复制源码。

历史证据中的工具安装目录、原始运行目录及板上部署目录有时会记录采集环境的路径，
用于追溯而不是脚本输入；不应据此假定对应目录存在，也不需要修改它们来复现流程。
发布包内的文件由同目录的 manifest 按 SHA-256 校验，加载不依赖历史构建目录。
板上的 `/home/xilinx/jupyter_notebooks/` 是部署目标示例，不是仓库源码路径。

`.Xil/`、Vivado `.cache/.runs/.sim` 和 Python `__pycache__/` 均为可再生缓存；
已验收的输入快照、日志、失败证据、汇总报告以及发布 `.bit/.hwh` 不属于缓存。
外部目录不在干净克隆的源码树中；本仓库只保留当前源码、可复现输入与有证据价值的结果。

## 产物和维护边界

- `.c/.S` 是CPU固件；HLS `.cpp` 描述硬件；`.sv/.v` 是硬件或仿真平台；Python在PS/电脑上运行。
- `.mem` 是存储镜像，用于仿真或RAM初始化；`.xdc` 是引脚/时序约束。
- `.xpr` 是Vivado工程；`.dcp` 是实现检查点；`.bit/.hwh` 是PYNQ配套部署文件。
- `.log/.rpt`、manifest、snapshot是执行证据；`.ipynb` 是演示Notebook。
- 新生成的HLS工程、Vivado工程、RTL/IP、波形、DCP及本地归档不提交Git；必要摘要与哈希提交到results。
- 不入Git不代表可以删除。冻结输入、已发布产物、失败证据和续跑依赖保留。
- 当前K4核心145/145与3.8028×属于RTL证据，不能记成新overlay的板上实测。
