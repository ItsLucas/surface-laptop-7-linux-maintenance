# SL7 Wi-Fi 故障核对

日志明确停在板级数据加载：`qmi-chip-id=2,qmi-board-id=255`，PCI subsystem-device 为 `1107`。这发生在热点扫描/连接之前，因此不能用重新输入密码解决。

读取本机 `/usr/lib/firmware/ath12k/WCN7850/hw2.0/board-2.bin.zst` 后，确认有 66 个板级名称、25 个板级数据块、1 个 regulatory 数据块。所需的 `1107/255` 名称不存在，但 `3378/255` 条目存在。

SL7 社区的 [fix-board-2-wifi.sh](https://github.com/bryce-hoehn/linux-surface-laptop-7/blob/main/fix-board-2-wifi.sh) 采用的就是给后者加前者的名称别名。本包使用你现有文件，保留所有已有条目与数据，增加这一别名；不替换成其他网站下载的一整套固件。来源相同不代表 RF 性能已在本机验证，仍需要实际启动、扫描与连接结果。

[Ubuntu bug 2130959](https://bugs.launchpad.net/ubuntu/+source/linux-firmware/+bug/2130959) 报告同型号机器、同一串失败标识，说明这不是你这次提取 ADSP 固件才首次出现的独有问题。当前日志只能确定存在该阻塞点，无法确定它在你安装前后的首次发生时间。

另有独立问题：SL7 社区项目仍列出 rfkill workaround；[上游 Romulus Wi-Fi 设备树提交讨论](https://lists.openwall.net/linux-kernel/2025/09/09/1747) 也说明默认触发的 rfkill 引脚需要 workaround。社区旧补丁是在 `ath12k_core_rfkill_config()` 提前返回，并非简单的 `rfkill unblock` 命令。[社区安装说明](https://github.com/bryce-hoehn/linux-surface-laptop-7) 将板级数据修复和内核 workaround 列为不同步骤。

因此本包安装板级别名，并提供重启后正常打开无线、检查软/硬阻止及扫描的脚本。没有提供未经匹配/签名验证的替代 .ko 或替换内核。你的日志驱动为 `ath12k_wifi7_pci`，社区旧脚本里的 `modprobe -r ath12k` 不能直接视为适合此版本的完整重载流程；本包采用重启验证。

成功判据：

1. 本次 `failed to fetch board data` / `qmi failed to load board data file:-2` 消失。
2. `iw dev` / NetworkManager 出现无线接口。
3. `rfkill list` 不再阻止无线，`nmcli device wifi list --rescan yes` 能扫描。
4. 通过 `nmtui` 实际连接，才能确认 Wi-Fi 已可用。

若第 1 项通过而后续失败，说明已越过当前阻塞点，需根据新日志继续检查 rfkill 或后续驱动/固件错误，不能把此次修复宣布为完整解决。

来源与文件：

- 原始压缩板级文件 SHA-256：`967bf1c70eff523be30dd4510920cd202c31cef0352c20dfc5d1d4bdafce29a9`
- 原始解压板级文件 SHA-256：`1abee7132dbccb523cca44a8de4e8968aa7bf5a5fcc032c338f687f94ea5bf4e`
- 增加别名后 SHA-256：`30ced6b4ba1968866ddf15c9d128860a9c0a44f430a41f278d9daa1a44e194b7`
- 上游独立复核工具：[Qualcomm ath12k-bdencoder](https://github.com/qca/qca-swiss-army-knife/blob/master/tools/scripts/ath12k/ath12k-bdencoder)，随包保留原始许可声明。
- 内核按名称选择数据的逻辑：[ath12k core.c](https://github.com/torvalds/linux/blob/master/drivers/net/wireless/ath/ath12k/core.c)。本包不改变发射功率、地区配置或 regulatory 数据。

可重建：`python3 tools/patch_board.py firmware/board-2.original.bin /tmp/sl7-board-rebuilt.bin`。输出已存在时拒绝覆盖。可用 `python3 tools/ath12k-bdencoder -i firmware/board-2.bin` 独立查看。
