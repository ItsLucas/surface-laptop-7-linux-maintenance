# Surface Laptop 7：最终维护包

当前已验证：Ubuntu 26.10、7.2.0-5-sl7、iptsd 3.1.0+sl7.2-1；Wi-Fi、蓝牙、触控板和SPI触摸屏可用，Secure Boot保持开启。默认启动已包含触摸屏，原正常内核保留回退。

先读[今日最终状态](docs/今日最终状态.zh-CN.md)，其中明确区分已修复内容与尚未解决的触控板热图缺失/睡眠功耗问题。

| 内容 | 入口 |
|---|---|
| 从安装至今的过程 | [完整记录](docs/安装以来的完整记录.zh-CN.md) |
| 当前全部补丁及来源 | [补丁清单](docs/补丁清单.zh-CN.md) |
| 以后升级内核 | [更新计划](docs/内核更新计划.zh-CN.md) |
| 精确版本重建 | [重建说明](docs/当前版本重建说明.zh-CN.md) |
| 最终状态与产物哈希 | validation/day-final-state.json、validation/current-artifacts.json |
| 按顺序应用的补丁 | patchsets/kernel/、patchsets/iptsd/、patchsets/iptsd-packaging/ |
| 当前配置和公开证书 | config/、certificates/public/ |
| 输入源码和打包文件 | sources/、kernel-packaging/、iptsd-packaging/ |
| 诊断、旧试验和Windows对照资料 | experimental/ |

旁边的sl7-recovery-20260914.tar.zst保存本机恢复用安装包、启动镜像/initrd、构建输入和固件。当前完整默认镜像是追加触摸屏设备树后的独立镜像；原内核deb仍作为基础模块包和原镜像回退，两者组合使用，详见恢复包README。

config/system-root是快照，不要整体覆盖根目录。旧build脚本记录当前版本制作过程，不能直接通过改版本号用于任意新内核。实验目录的旧“未安装/等待批准”记录按时间保留，当前状态以今日最终状态和validation/day-final-state.json为准。

不含签名私钥、MOK口令、Wi-Fi认证配置或蓝牙配对密钥。部分配置包含本机MAC、磁盘UUID和历史鼠标地址；对外分享优先挑选通用补丁与精简证据。
