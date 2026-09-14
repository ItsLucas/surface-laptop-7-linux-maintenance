**Surface Laptop 7 X1E：Wi-Fi、触控板与 Secure Boot 研究记录**

调查日期：2026-09-14。对象是这台 13.8 英寸 Surface Laptop 7，Ubuntu 26.10 开发版，`7.2.0-5-generic`，ARM64，设备树标识 `microsoft,romulus13`。本次读取了系统状态、公开源码、问题讨论及软件包头部；没有安装软件、重载驱动、修改启动配置、导入密钥或重启。

结论是：**Wi-Fi 已完成硬件与固件初始化，当前被驱动报告的硬阻断挡住；触控板所需的设备树、内核驱动和用户态支持尚不完整。** 两者都有社区修复方向，但现成社区内核不能直接满足这台机器保留 Secure Boot 的要求。原始现场摘要见 [evidence.json](evidence.json)。

| 项目 | 本机实测 | 判断 |
|---|---|---|
| Wi-Fi | WCN7850 hw2.0 / PCI `17cb:1107`，驱动 `ath12k_wifi7_pci`，接口已创建 | 硬件识别和固件启动已成功 |
| 无线开关 | `phy0: soft=0, hard=1`，NetworkManager 显示硬件无线关闭 | 当前直接阻断是 hard rfkill |
| Wi-Fi 板级固件 | `updates/ath12k/WCN7850/hw2.0/board-2.bin` 已包含社区要求的别名 | 重复运行旧固件修复脚本没有明确收益 |
| 触控板设备树 | SPI 控制器禁用，无 `touchpad` / `hid-over-spi` 节点 | 内核没有枚举触控板 |
| 触控板软件 | 无 `CONFIG_SPI_HID` / `spi-hid`，无 `iptsd`；现有 SPI 模块不匹配社区所需 GENI QSPI 类型 | 需要配套驱动、设备树与用户态处理 |
| Secure Boot | `SecureBoot enabled`，lockdown 为 `integrity` | 当前保护有效，后续须保留 |
| 当前内核镜像 | Canonical 签名，内含 `.linux`、`.dtbauto`、`.hwids` | 修复设备树时必须考虑最终签名镜像的打包 |

Wi-Fi 的 hard block 是 Linux 收到的驱动状态，并不能据此认定有物理开关被拨动或网卡损坏。内核把 hard block 与可由用户态控制的 soft block 分开处理；`rfkill unblock` 不能覆盖 hard block。[Linux rfkill 文档](https://www.kernel.org/doc/html/latest/driver-api/rfkill.html)

本机 Wi-Fi 的运行固件为 `WLAN.HMT.1.1.c7-00108-QCAHMTSWPL_V1.0_V2.0_SILICONZ_UPSTREAM-3`，芯片上报 `chip_id=2, board_id=255`。已经安装的固件覆盖文件把 `subsystem-device=1107,qmi-board-id=255` 与社区借用的 `subsystem-device=3378,qmi-board-id=255` 指向相同板级数据。这与仓库脚本的修改一致；本次未跟踪固件加载器以独立证明实际选用了哪个文件，但启动日志没有缺固件错误，接口也已建立。[固件修复脚本](https://github.com/bryce-hoehn/linux-surface-laptop-7/blob/main/fix-board-2-wifi.sh)

社区的对应 rfkill 补丁在 `ath12k_core_rfkill_config()` 中提前返回，绕过后续配置。项目 issue #1 有正确加载补丁内核后 Wi-Fi 恢复的报告，也有速度偏慢记录。**本机症状高度吻合这一兼容性问题，但尚未通过修复后的内核进行实机验证，底层错误信号的具体来源也未确定。** 该补丁是临时绕过方式，不能当作完善的机型专用修复。[rfkill 补丁](https://github.com/bryce-hoehn/linux-surface-laptop-7/blob/main/patches/0001-wifi-rfkill-hack.patch)、[Wi-Fi 讨论](https://github.com/bryce-hoehn/linux-surface-laptop-7/issues/1)

7.2 的 `ath12k_wifi7` 模块拆分没有把该函数移出共享 `ath12k/core.c`。旧补丁能在本次获取的上游 master 上通过带 fuzz 的 dry-run，但这不等于已经验证 Ubuntu `7.2.0-5.5` 源码、编译结果、模块 ABI 或签名。当前可见模块参数也没有 `disable_rfkill=1` 这样的现成开关。[上游共享驱动源码](https://github.com/torvalds/linux/blob/master/drivers/net/wireless/ath/ath12k/core.c)

触控板方面，SAM 内置键盘正常，不能因此推定触控板通道也存在。当前 `/sys/bus/spi/devices` 为空，输入设备中没有触控板。社区 ELLX 的 Romulus 设备树显式启用 SPI19，使用 `qcom,geni-spi-qspi`，并创建 `compatible="hid-over-spi"` 的触控板子设备；同时依赖修改后的 GENI QSPI、GPI DMA 与 `CONFIG_SPI_HID` 驱动。本机现有 `spi_geni_qcom` 和 `spi_qcom_qspi` 均没有匹配这个 GENI QSPI 类型。[ELLX 设备树](https://github.com/ProgrammerIn-wonderland/ELLX-Kernel/blob/7.0.0-rc4-10-sl7/arch/arm64/boot/dts/qcom/x1e80100-microsoft-romulus.dtsi#L1771)、[HID-over-SPI 配置](https://github.com/ProgrammerIn-wonderland/ELLX-Kernel/blob/7.0.0-rc4-10-sl7/drivers/hid/spi-hid/Kconfig)

这些内核组件工作后，社区方案还用 `alex-lentz/iptsd` 读取原始数据并生成输入事件。因此单装 `iptsd`、修改 GNOME 设置或换 libinput 驱动，无法补齐本机当前缺失的设备枚举。社区已报告触控板移动、多指手势和触觉点击可用；这是 ARM 机型项目的使用记录，不能把 Intel Surface 的内核驱动说明直接套到 X1E 上。[触控板讨论 #5](https://github.com/bryce-hoehn/linux-surface-laptop-7/issues/5)、[iptsd 分支](https://github.com/alex-lentz/iptsd)

后续仍要分别验证 iptsd 的 udev/systemd 集成、校准和休眠恢复。Issue #23 有预编译 iptsd 包缺少服务模板或规则的报告；仓库也仍记录休眠后触控板可能进入异常状态，进入 Windows 后再返回 Linux 是已知恢复办法之一。这些属于后续运行问题，不能解释为本机目前唯一缺少某个服务。触控板可用也不代表触摸屏已支持。[iptsd 打包问题 #23](https://github.com/bryce-hoehn/linux-surface-laptop-7/issues/23)、[项目说明](https://github.com/bryce-hoehn/linux-surface-laptop-7)

Secure Boot 的现场证据比 BIOS 设置本身更完整：`mokutil --sb-state` 为 enabled，内核日志明确进入 Secure Boot lockdown，`/sys/kernel/security/lockdown` 为 `none [integrity] confidentiality`。磁盘上的 ARM64 shim 带 Microsoft UEFI CA 签名，GRUB 和现用内核镜像带 Canonical 签名；未发现已登记的自定义 MOK 或待导入项。用户所要求的 Microsoft & Third-Party CA 模式应继续保留。[Ubuntu ARM64 Secure Boot 说明](https://documentation.ubuntu.com/security/docs/security-features/platform-protections/secure-boot/)

当前 `vmlinuz` 是包含内核与多份设备树的 PE 镜像，布局符合 Ubuntu Stubble。已提取其中 Romulus13 的 `.dtbauto`：与 `/boot/dtb-7.2.0-5-generic` 字节完全相同，同样没有触控板节点。因此不能把“编辑 `/boot/dtb`”直接当作完整修复；需要把修复后的设备树放入实际使用的启动镜像，并对最终镜像重新签名。Ubuntu Stubble 正是为设备树随内核打包、签名和经 GRUB 验证而设计。[Ubuntu Stubble](https://github.com/ubuntu/stubble)

此外，上游 GRUB 将 `devicetree` 注册为 lockdown 限制命令，内核 EFI stub 在 Secure Boot 下忽略命令行 `dtb=`。这些源码限制说明，执行前必须验证正确的设备树加载路径；不能假设换一个裸 DTB 或追加启动参数即可生效。[GRUB 源码](https://github.com/rhboot/grub2/blob/master/grub-core/loader/efi/fdt.c)、[Linux EFI stub 源码](https://github.com/torvalds/linux/blob/master/drivers/firmware/efi/libstub/fdt.c)

MOK 可以用于在保持 Secure Boot 验证的同时信任本机自签名组件。需要区分两种签名：完整启动 PE 镜像使用 `sbsign`；内核模块使用内核的 `scripts/sign-file` 等工具。本机 `/usr/lib/shim/mok/openssl.cnf` 默认带 `1.3.6.1.4.1.2312.16.1.2`，即仅限模块签名；shim 15.4 及以后不会用这种证书验证启动内核。若需要完整定制内核，证书用途必须允许启动镜像验证，模块签名信任也须同时成立。本次没有生成、导入或登记任何密钥。[Ubuntu 对 MOK 用途的说明](https://documentation.ubuntu.com/security/docs/security-features/platform-protections/secure-boot/)、[内核模块签名文档](https://docs.kernel.org/admin-guide/module-signing.html)

启动参数虽包含 `efi=noruntime`，本机仍存在 EFI 变量接口，`mokutil` 可读，日志也有 Qualcomm UEFI 安全应用客户端。现有证据不足以保证实际 MOK 写入流程一定成功，但不能仅凭这个参数断言 MOK 不可用；也没有理由为研究而移除它。

对现成社区包的核查结果如下。项目 README 明确写的是在 Ubuntu concept **26.04** 上测试；README 举例 `7.0.0-rc4-11`，本次 ELLX 发布目录已提供 `7.0.0-rc4-12`，说明文档与发布目录不同步。核查的最新版包为 `7.0.0~rc4-g0e9944fa4cf2-44`、ARM64；公开目录及所查源码分支中未找到 7.2 对应版本。这不构成支持 Ubuntu 26.10 的保证。[ELLX 发布目录](https://public.hgci.org/software/ELLX/kernels/)、[ELLX 源码](https://github.com/ProgrammerIn-wonderland/ELLX-Kernel)

通过读取 `-12` 软件包的部分数据，提取到了其中 `vmlinuz` 的 ARM64 PE32+ 头；其 Security Directory 的文件偏移和长度均为零，**该包中的启动内核没有 Authenticode 签名**。该检查只读取了包的一部分，不代表验证了完整包内容，但足以判断不能把它当作可直接通过现有 Secure Boot 信任链的内核。旧 rc 内核在 26.10 上的其他硬件回归也尚未评估。[本次检查的发布目录](https://public.hgci.org/software/ELLX/kernels/7.0.0-rc4-12/)

Ubuntu concept 的 SL7 支持跟踪项仍为 Confirmed/Wishlist，本次读取的 API 最后更新日期为 2025-07-21，不能用它证明 26.10 已完整支持。ELLX 的自制安装镜像目录另有作者关于启用音频后扬声器损坏的报告，文末又表示可能已经修复；这不足以证明其安装镜像适合直接采用，也不能扩大为所有 ELLX 内核必然损坏硬件。这里把 ELLX 作为目标功能的源码参考，不把自制 ISO 当作本机修复步骤。[Ubuntu 支持跟踪](https://bugs.launchpad.net/ubuntu-concept/+bug/2084951)、[ELLX 安装镜像作者说明](https://public.hgci.org/software/ELLX/installer/README-YOU-ARE-IN-GRAVE-DANGER.txt)

建议把后续实施分为两个独立步骤，均保持当前官方启动项作为回退：

1. **先解决 Wi-Fi。** 获取与 `7.2.0-5.5` 精确匹配的 Ubuntu 源码，评估为 SL7 限定作用范围的 rfkill 修复。优先验证能否只重建必要模块并使用受信任 MOK 签名，以保留现用 Canonical 内核与设备树。能否独立替换、ABI 和依赖是否满足，须以实际构建结果为准；当前尚未编译或加载。
2. **再解决触控板。** 将所需 GENI QSPI/GPI/HID-SPI 支持及 Romulus13 设备树作为配套变更移植到目标内核，加入对应 iptsd。保留当前打包方式，对包含新设备树的最终启动 PE 镜像签名，并验证模块信任。仅有较新的版本号，不代表包含这些尚未具备的机型支持。
3. **实施前给出具体可审核材料。** 包括源码版本、补丁差异、构建产物、签名检查、MOK 证书用途与指纹、独立启动项和回退步骤。涉及模块卸载、安装内核、导入 MOK、更新启动配置或重启时，先取得用户批准。MOK 最终登记通常需要用户在启动时的管理界面确认。
4. **实施后按层验收。** Wi-Fi 检查 hard block 清除、扫描、关联、稳定性；触控板先检查 SPI/HID 设备出现，再检查 iptsd 生成输入设备、移动、点击、滚动和休眠恢复。每一步同时复核 Secure Boot 与 lockdown 状态。

本次研究没有证明物理硬件是否损坏，也没有完成修复后的实机运行验证。已能确定的是当前软件支持链的具体缺口，以及保持 Secure Boot 时必须满足的打包和签名条件。
