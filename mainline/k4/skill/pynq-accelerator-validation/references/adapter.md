# 测试计划与适配器协议

命令从 `skill/pynq-accelerator-validation/` 执行。运行器与示例仅依赖 Python 3.6+ 标准库；板上适配器所用 PYNQ/NumPy 由目标镜像提供。PC 离线运行不需要安装 PYNQ。

## 可直接复现的跨题目示例

```console
python scripts/validate_accelerator.py assets/vector_demo.plan.json --adapter assets/vector_demo_adapter.py --output ../../results/skill_checks/vector_demo
```

该例覆盖普通向量、饱和边界和空向量；3 个用例 × (1 次预热 + 5 次重复) = 18 次黄金比对，性能统计仅包含15次实测调用。`offline-demo` 明确表示 PC 上的软件示例，其微秒级耗时没有 FPGA 性能含义。黄金输出在计划中手工固定，不调用被测实现生成。

## JSON 计划

| 字段 | 要求 |
|---|---|
| `schema` | 整数1 |
| `measurement_kind` | `offline-demo` 或 `board-live`，与适配器及 session 证据一致 |
| `warmup/repeats` | 非负整数/正整数，均按整个 cases 集合执行 |
| `timeout_seconds` | 每次 run 的正有限秒数，传给驱动并在返回后复核 |
| `cases` | 非空数组；每项有唯一字符串 `id`、JSON兼容的 `input/expected` |
| `tolerance` | 可选 `atol/rtol`，默认均为0；有限非负值 |
| `metadata` | 黄金数据来源、版本、板型、part、镜像、PYNQ版本、频率条件等说明 |
| `adapter_config` | 适配器私有配置，运行器不解释寄存器或板卡常量 |
| `artifacts` | 可选、相对计划文件的制品路径数组，额外记录 SHA-256 |
| `resources` | 可选资源报告列表，见下文 |

数据比较支持嵌套列表、字典、数值、字符串、布尔和 null。长度、键集合必须一致；布尔不视为整数。`abs(actual-expected) <= atol + rtol*abs(expected)` 只作用于数值叶子；NaN/Infinity 不通过。字节序、整数位宽、定点符号位和 ndarray dtype 必须在适配器编码阶段明确，JSON 本身不表达 dtype。字节输出建议用统一小写 hex 字符串；密码结果用精确比较。

## 适配器最小接口

```python
MEASUREMENT_KIND = "board-live"

class Session:
    def __init__(self, driver):
        self.driver = driver

    def describe(self):
        return {
            "measurement_kind": MEASUREMENT_KIND,
            "board": "实际板型",
            "pynq_version": "实际版本",
            "overlay_sha256": "实测制品哈希",
            "hardware_identity": {"id": 123, "abi": 1}
        }

    def run(self, value, timeout):
        # driver.execute 是你的驱动接口，须在内部实施超时。
        output = self.driver.execute(value, timeout=timeout)
        return {"output": output}

    def close(self):
        self.driver.close()

def create(plan, directory):
    # 实现自己的 load_verified_driver；确认 Overlay/ABI 后分配会话资源。
    driver = load_verified_driver(plan["adapter_config"], directory)
    return Session(driver)
```

这是需按设备补全的协议示意；可直接运行的例子在 `assets/vector_demo_adapter.py` 和 `assets/mlkem1024_board_adapter.py`。后者委托已有驱动完成已验证的 MMIO/固件流程。

- `create` 一次/会话，耗时不计入每用例墙钟。如果中途分配失败，适配器须在抛出前清理已分配资源。
- `describe` 返回有限数值组成的 JSON-compatible 字典，记录真实环境和制品身份。`board-live` 是可审计标签，不是远程硬件认证。
- `run(input, timeout)` 顺序执行，不支持同一硬件会话并发。至少返回 `output`；可返回 JSON-compatible `detail`。可选设备时间必须同时给出非负整数 `device_cycles`、正有限 `frequency_hz` 和字符串 `cycle_scope`。
- `close` 在 create 成功后的任何退出路径调用。按驱动协议停机并释放缓冲区，失败也要报错，不能吞掉清理异常。

传入的测试输入每次从固定 JSON 重建。输入传输、等待、回读若在 `run` 中执行，均计入墙钟；黄金比较由运行器在计时之外进行。若现有驱动内部已经验证结果，该内部验证仍计入 adapter.run，需披露。

## 接入本队现有发布包

先在 PC 生成与现成向量绑定的计划，不访问板卡：

```console
python scripts/make_mlkem_plan.py --bundle ../../release/mlkem1024_pynq --output ../../results/skill_checks/mlkem_plan.json --indices 0 1 115 --repeats 3
```

把整个已校验发布包与技能目录放到板上，使用板上的 bundle 路径重新生成计划。新板上运行命令：

```console
python scripts/validate_accelerator.py ../../results/skill_checks/mlkem_plan.json --adapter assets/mlkem1024_board_adapter.py --output ../../results/skill_checks/mlkem_board_run
```

该命令通过现有 `MLKEM1024.load` 下载 Overlay；运行时计划中的目录必须指向板上发布包，不可保留 PC 的 `E:` 路径。`--mode cpu_only` 仅适用于有 `paired_firmware` 的成对固件发布包。生成器先调用既有 `verify_bundle`，其向量形状、哈希和版本约束继续生效。全部145用例可将 `--indices` 换为0到144的完整列表；默认的3例只构成 smoke，不能宣称 FULL_PASS。

迁移至滤波/FFT/图像类题目时，删除项目适配器依赖，改为自己的驱动和独立黄金向量，运行器不变。改变板卡只需要适配器及制品配置变化；板上驱动和 Overlay 本身仍须重新构建/验证。

## 资源数据

计划中可加入：

```json
{
  "resources": [
    {"path": "reports/my_core_csynth.xml", "kind": "hls-csynth-xml", "stage": "hls-estimate", "scope": "my_core"},
    {"path": "reports/utilization.rpt", "kind": "vivado-utilization", "stage": "implementation", "scope": "my_system_top"}
  ]
}
```

这是并入现有计划的字段片段，不是完整测试计划。路径相对计划所在目录；报表为用户已有的 EDA 产物，工具不自行启动 Vivado/Vitis。

HLS XML 读取 `AreaEstimates/Resources`，额外记录 part/top/estimated_clock_ns；未知资源数量直接失败。Vivado 文本支持 Slice/CLB LUTs、Slice/CLB Registers、Block RAM Tile、DSPs/DSP48E1/DSP48E2 的 Used 列，保留资源原单位；`BRAM_TILE` 可为0.5，不与 HLS `BRAM_18K` 直接相加。未出现的资源不补零。文本必须有 `Design State`，`implementation` 只接受 Routed/Placed/Optimized，`synthesis` 只接受 Synthesized；解析不支持的版本应补适配与样例测试后再使用。

每份报告独立带 `scope/stage/path/sha256`，不会把单 IP 资源伪装成整系统资源。当前未解析时序 slack、功耗或 Fmax；利用率报告不能证明时序收敛。

## 产物和退出约定

- `report.json`：plan/adapter/runner 哈希、环境、逐次结果、输入/黄金/输出摘要、失配位置、设备周期、资源证据和清理错误。
- `report.md`：可读结论、每用例样本数/median/P95/max、资源口径和缺失项说明。
- 成功退出0，任何计划/加载/比对/驱动/资源/清理错误退出1。创建全新输出目录可保留不同轮次；同一路径会覆盖前次报告。

统计使用 `(n-1)*p` 线性插值。`wall_seconds` 总体统计混合所有用例，各操作性能比较应看 `per_case_wall_seconds`；失败留下的成功样本仅供定位，`performance_eligible=false` 时不能当验收结果。工具不计算吞吐或加速比：需要统一负载大小、频率、批次和计时口径后再做比较。
