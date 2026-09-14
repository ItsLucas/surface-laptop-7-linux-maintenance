# Surface Laptop 7 Linux maintenance archive

Microsoft Surface Laptop 7 13.8 英寸（X1E / Romulus13）在 Ubuntu 26.10 上的内核补丁、iptsd 补丁、系统配置、验证证据及恢复资料。

当前实机状态：Wi-Fi、蓝牙、触控板和触摸屏均可用；Secure Boot 保持开启，自定义内核及模块由已登记的 MOK 签名。触摸屏仍需继续验证睡眠恢复与完整功耗管理。

- [今日最终状态](docs/今日最终状态.zh-CN.md)
- [维护包说明](README.zh-CN.md)
- [内核更新计划](docs/内核更新计划.zh-CN.md)
- [补丁清单](docs/补丁清单.zh-CN.md)
- [完整安装记录](docs/安装以来的完整记录.zh-CN.md)
- [2026-09-14 归档及恢复包](../../releases/tag/v2026.09.14)

Release 中提供：

- `sl7-maintenance-20260914.tar.zst`：可审计的维护资料归档。
- `sl7-recovery-20260914.tar.zst`：内核、initrd、签名启动镜像、软件包、构建输入和恢复资料。
- `RELEASE-SHA256SUMS`：两个归档的 SHA-256。

归档不含签名私钥、MOK 口令或网络认证资料。硬件支持仍属于实验性质，应用内核、设备树或恢复操作前请阅读相应说明并保留原启动项。
