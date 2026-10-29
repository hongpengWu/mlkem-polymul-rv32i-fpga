---
name: pynq-overlay-contract
description: 为 PYNQ Overlay 建立可迁移的接口契约，校验 bit/hwh 配对、哈希、AXI 地址与硬件 ID/ABI，提供 register_map 和 MMIO 访问及超时定位流程。适用于 Overlay 交付、换板迁移和寄存器接口联调。
---

# PYNQ Overlay 契约与加载校验

将板卡地址、IP 层级名、身份寄存器与访问语义移入 JSON 契约。使用同一检查器处理滤波、FFT、图像、密码或自定义控制 IP；仅项目示例包含 ML-KEM 常量。

## 执行流程

1. 先读 [接口契约与用法](references/contract.md)，从硬件头文件、RTL 与 HWH 确认地址、寄存器语义和 ID/ABI。不要把 HLS 的 `ap_ctrl_hs` 套到自定义状态机；不确定的寄存器不写入。
2. 从 `assets/vector.template.json` 建立新契约。用 `scripts/seal_contract.py` 记录经确认的 bit/hwh SHA-256；哈希封装不证明其适合目标器件。文件必须为同名 `.bit/.hwh`，保存在同一个制品目录。
3. 默认执行 `scripts/overlay_contract.py contract.json --bundle-dir <制品目录>`，先完成无硬件检查。检查失败则定位文件版本、地址或契约，不下载 PL。
4. 在用户要求板上运行、已确认目标器件与板卡的场景，添加 `--download`，依次验证、创建 `Overlay(download=False)`、检查 `ip_dict`、下载、读取稳定的 ID/ABI。已有 overlay 的 Python 调用可使用 `connect(download=False)`，它会先检查 `is_loaded()`。
5. 使用 `RegisterIO` 完成命名寄存器访问与有界轮询；仅对契约中明确允许的寄存器写值。需要 `register_map` 时按接口文档的范式检查字段和副作用。
6. 保留 JSON 输出、契约、制品哈希与环境信息。明确区分离线通过与硬件身份验证通过。

## 保留的接口约束

- 地址均为 IP 内的字节偏移，32 位对齐，不把物理基地址再次加到偏移上。
- `ro/rw/wo/w1c/rc` 有不同语义；快照只读显式启用的 `ro/rw`。W1C/命令寄存器禁止通用读改写，读清寄存器不自动打印。
- module-reference IP 可能没有 `ip_dict` 项。只有 HWH 精确地址范围校验通过且契约显式允许时，才使用 `MMIO` 回退；硬件 ID/ABI 仍须通过。
- 超时后收集安全状态，不自动重试启动、不凭空写复位位。轮询超时无法中断阻塞在 AXI 总线上的一次 MMIO 读取。
- 由 `connect()` 返回的 Overlay 对象需保留至会话结束；该封装按单调用者使用，不支持多个 Notebook 并发操作同一 IP。

## 资源与验证

- [契约格式、PC/板上命令、register_map 范式](references/contract.md)
- [症状、触发条件、排查顺序与迁移边界](references/troubleshooting.md)
- `assets/mlkem1024.contract.json`：从本项目现有发布包提炼的实例，不是新题目的默认参数。

已验证内容与经验出处见 [技能包总说明](../README.md)。更换板卡需重建面向目标器件的 bit/hwh、重新封装契约；本 Skill 复用的是流程和工具，不是跨器件通用的比特流。
