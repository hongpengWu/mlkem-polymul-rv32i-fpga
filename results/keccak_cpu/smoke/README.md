# PicoRV32 + Keccak 接口闭环

日期：2026-09-27。10/10调用、216/216结果字通过；直接观测HLS的10次启动与10次完成。
这是真实PicoRV32 RV32IM-fast执行C驱动的RTL仿真，四种FIPS202模式均调用硬件，无软件哈希回退。
128KiB程序RAM、32KiB栈；固件4888B。独立HLS保持opt02版，未修改原CPU-only基线。

| 调用 | 输入→输出B | 返回值 | CPU调用周期 | 硬件busy周期 |
|---|---:|---:|---:|---:|
| H_ek_1568 | 1568→32 | 0 | 16,683 | 1,260 |
| J_z_ciphertext_1600 | 1600→32 | 0 | 16,944 | 1,276 |
| G_64 | 64→64 | 0 | 4,983 | 207 |
| XOF_first_13 | 34→13 | 0 | 4,321 | 133 |
| interleaved_SHAKE256_7 | 33→7 | 0 | 4,259 | 123 |
| XOF_continue_491 | 0→491 | 0 | 8,341 | 735 |
| XOF_continue_168 | 0→168 | 0 | 5,395 | 296 |
| clear_context | 0→0 | 0 | 3,815 | 31 |
| reject_squeeze_after_clear | 0→17 | -2 | 3,773 | 5 |
| reject_SHA3_output_length | 0→31 | -1 | 3,773 | 4 |

调用合计：CPU 72,287 cycles；硬件busy 4,070 cycles。
完整TB含初始化和调试输出共326,618 cycles；100MHz仅为仿真时钟，尚未完成CPU集成系统布局布线。
CPU调用周期包含context搬入/读回、输入/输出搬运、配置、等待和统计寄存器读取；不含测试sentinel初始化。
硬件busy从HLS启动控制写握手到完成中断被adapter观测，不是裸permutation周期。
没有同形状CPU-only微基准，不据此计算加速比。完整K4官方加速KAT和API对照仍待接入。

## 覆盖和证据

覆盖K4 H(ek)=1568B、J(z||c)=1600B、SHA3-512、两个上下文切换、13+491+168B续取、CLEAR、无效context及SHA3长度错误。
返回值、全部输出字、部分字补零、CPU上下文不变/清零、累计搬运计数和HLS执行计数均由TB校验。
错误调用检查调用方输出不变；本轮不直接检查硬件输出BRAM的全部未写单元，独立HLS回归单独保留。
预期值由Python hashlib生成并只载入TB，CPU固件不含预期摘要。
- [运行原始日志](20260927_164834_167894/simulate.txt)
- [运行前RTL/固件/fixture哈希](20260927_164834_167894/manifest.json)
- [编译命令和源码/输入哈希](build.json)
- [逐调用数据](summary.json)

失败断点均保留在E:/hls/k4cpu：164543为Vivado不可修改.dat文件类型，修复Tcl；
164659为CLEAR退出时HLS流水线产生EN=1/WEN=0的一次地址0xd0无效读取，adapter误记错误。
现在精确丢弃CLEAR的这次退出探测，不访问RAM；其他越界仍记错，写入边界未放宽。最终164834全部通过。

## 重现

```powershell
python scripts/mlkem1024_keccak/build_smoke.py
python scripts/mlkem1024_keccak/run_smoke.py
```

运行器要求已验证HLS opt02输出（可用--hls-run传入），核对源码/TB/RTL哈希，冻结新目录运行，保留失败断点；HLS生成RTL不进Git。
地址、接口和后续移植见[接口说明](../../../docs/MLKEM1024_KECCAK_CPU_INTERFACE.md)。
