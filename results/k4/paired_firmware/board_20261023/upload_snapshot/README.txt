ML-KEM-1024 同板 CPU-only / CPU+Keccak 对照

在 Jupyter 打开本目录 mlkem1024.ipynb，选择 Kernel -> Restart & Run All。
默认执行两组各145条官方测试、三种操作各10次重复、复位/无效输入/超时恢复。
全部代码已写入Notebook，无需终端命令。每阶段立即保存独立JSON；最后下载汇总证据。
仅打开本目录一个Notebook运行，等待全部单元完成。Notebook可正常保存。

两组使用同一bitstream、RV32IM、100MHz、128KiB RAM/32KiB栈。CPU-only为软件FIPS202，
加速组为Keccak硬件服务。两组切换时CPU保持复位，全部RAM镜像写入并逐字读回核验。
固件装载/读回耗时单列，不计入API和用例墙钟；墙钟包含PS传输、等待和结果核对。
本包已通过本地主机测试与7例真实RTL切换测试；实板结论以本次运行JSON为准。
此对照不测移除加速器后的面积/功耗，也不将历史RTL数据作为实板对照。
