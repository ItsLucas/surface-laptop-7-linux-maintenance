**MSHW0461/GTCH SPI 触摸屏与触控板参数核对：已批准并安装单次启动项，等待重启实测。**

Windows 原始证据已从 U 盘复制到 `../touchscreen-test/windows-results-20260914/`，64 个清单文件哈希全部通过。PnP 中实际触摸屏为 `HID\MSHW0461&COL03`，父设备 `ACPI\MSHW0461`，路径 `ACPI(_SB_)#ACPI(GTCH)`，服务 `hidspi`。控制器 `SP11` 的 MMIO 是 `0xa88000`，对应 Linux **SPI10/QUP1 SE2**。

旧 I2C 0x34 方案属于 SSDT 的 ITCH/MSHW0468 另一硬件分支。本次候选从正常组合内核的 DT 基线构建，完全撤去了该 I2C 实验节点，不再对此地址或 GPIO31 试复位。

**本次镜像**

- 文件：`sl7-spi-touchscreen-test.efi`
- SHA256：`94003dc6c6c1e194054037ced995eb2258a08e1c346acaaf0964a37c673e927f`
- 仍用现有 `7.2.0-5-sl7` 内核、全部原驱动和原 initrd。只有外层镜像的 `.dtbauto` 节不同，内层内核与其他节逐字节相同。
- 已用现有启动 MOK 签名并验证；该证书已登记。Secure Boot 保持开启，无需新密钥或重新登记。

**设备树与电源设计**

| 参数 | 选用值与依据 |
|---|---|
| SPI10 | `qcom,geni-spi-qspi`，GPI DMA1、SE2、QSPI protocol4 |
| 速度 | 20 MHz，使用现有驱动的已用速度，低于 Windows 资源的40 MHz上限 |
| 引脚 | GPIO40/41/42 数据时钟、GPIO43 CS0；由SoC pinctrl可选功能及IRQ51排除关系推导额外数据线GPIO49/50，仍需实机验证 |
| 中断 | GPIO51，下降沿，输入上拉；按GTCH ACPI实际资源描述 |
| 复位 | GPIO48，低有效；现有驱动已使用300 ms复位脉冲，与ACPI `_RST` 一致 |
| 电源使能 | GPIO64，高有效，固定开关模型；**没有猜测或编程供电电压** |
| 上电延时 | regulator启动等待500 ms；供电依赖注册完成后，HID驱动才执行复位序列 |
| 本轮电源策略 | `boot-on` + `always-on`，确保复用现有驱动时供电先稳定。先验证活动态功能，不宣称完成休眠节能 |
| GPIO896 | 超出本机Linux TLMM 239线范围，不映射为物理GPIO。现有驱动使用一个 `spi->irq`，活动态由GPIO51处理。Windows该辅助资源的精确语义、唤醒行为仍未确认 |

已核对原有 1,419 个节点，处理 phandle 重新编号后，只有 SPI10 和 GPI DMA1 的目标配置改变，另新增触屏电源/引脚/子设备。触控板 SPI19、其供电GPIO65/复位GPIO120、中断GPIO3、Wi-Fi、蓝牙、USB节点均保持原配置。驱动和内核未重新编译或替换。

现有 `spi_hid` 的邮箱地址0x1000/0x1004/0x2000、读写opcode0xEB/0xE2，与本机GTCH/HSPI的DSM一致。这支持复用协议实现，但还没有读到触摸屏的实际HID描述符；报告长度、IRQ处理和input枚举仍待本机启动验证。Microsoft PnP文档也将PNP0C51定义为HID-over-SPI，并描述复位响应、设备描述符、报告描述符的枚举顺序：[文档](https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/plug-and-play-for-spi)。

**触控板一并对齐的结果**

使用当前已安装 iptsd fork 的同一套解析代码，只读查询了实际触控板的元数据，没有切换设备模式：18行、26列、宽12cm、高8cm、InvertX=false、InvertY=false，全部与Windows CurrentParams的可验证字段一致。内核uinput暴露的轴范围/分辨率也对应120×80mm。

原 `/etc/iptsd.d/91-calibration-045E-0C77.conf` 与最终存档逐字节一致，继续使用 SizeMin=0.8、SizeMax=2.0、AspectMin=1.0、AspectMax=2.1。既有参数已一致，故不重复安装92几何覆盖，也不把Windows未解释的浮点数、指针速度、AAP参数或专有DLL当成iptsd原生参数。不能声称Windows处理算法已经移植。

**批准后执行与回退**

1. 备份当前GRUB配置，把候选镜像安装到 `/boot/sl7/7.2.0-5-sl7-spi-touchscreen-test/kernel.efi`。
2. 安装 `/etc/grub.d/45_sl7_spi_touchscreen_test`，entry ID为 `sl7-spi-touchscreen-test`，复用原initrd和 `efi=noruntime` 参数。
3. 将已确认不适用于本机的旧I2C测试菜单脚本移入备份；保留其历史镜像与诊断资料。正常默认仍是 `sl7-combined-kernel`，5秒菜单保留。
4. `grub-reboot sl7-spi-touchscreen-test` 只安排下一次启动，用户保存工作后自行重启。
5. 验证SPI10/HID描述符、触摸输入与方向、多指动作，并回归触控板、Wi-Fi、蓝牙、USB与Secure Boot。新设备可能改变spi/hidraw编号，按VID/PID和设备路径识别，不假定原编号。

失败时重新启动选择正常组合内核。首次启用新的控制器和引脚可能导致设备不响应或启动异常，所以安装和单次测试需要用户批准；现已安装独立SPI测试项，旧I2C测试菜单已退役，next_entry=sl7-spi-touchscreen-test；当前正常默认仍保留，尚未重启启用SPI10。
