# SL7 触摸屏 Windows 证据交接 — 2026-09-14

结论：本机正在工作的触摸屏是 `MSHW0461 / \_SB.GTCH`，使用 HID over SPI；之前测试的 `I2C 0x34 / GPIO31 / GPIO38` 属于 SSDT 中另一硬件分支 `ITCH / MSHW0468`。应停止沿该 I2C 节点继续试复位，转向 QUP1 SE2 的 SPI/QSPI。这里提供的是已核实的 Windows 资源与 Linux 修改依据，尚未在 Linux 验证触摸屏修复。

用户本轮确认 Windows 手指触摸正常；Linux WiFi、Bluetooth、touchpad、USB 已恢复。D 盘已不可用，交接包通过 U 盘带回 Linux。保留已有功能、触摸板校准、Secure Boot/MOK 签名链和正常启动项。

## 设备身份：现场 PnP 证据

见 `windows-raw/target-pnp.json`（2026-09-14 17:15 +08:00）：

- `HID\MSHW0461&COL03`，名称 Surface Touch Screen Device，HardwareIds 包含 `HID_DEVICE_UP:000D_U:0004`，状态 OK。
- 父设备 `ACPI\MSHW0461`，LocationPaths 为 `ACPI(_SB_)#ACPI(GTCH)`，兼容 ID `PNP0C51`，服务 `hidspi`，INF `hidspi_km.inf`，版本 `10.0.26100.8972`，ProblemCode 0。
- 控制器 `ACPI\QCOM0C0E\B`，LocationPaths `ACPI(_SB_)#ACPI(SP11)`，服务 `qcspi`，INF `oem100.inf`，版本 `1.0.4160.6000`。
- 触摸板是独立的 `MSHW0238 / HSPI / SP20`。不要把触摸板资源改成触摸屏资源。

原采集脚本只检查 CompatibleIds，因此打印了候选数 0；这台机器把 usage 放在 HardwareIds，CompatibleIds 为空。这不是触摸屏未识别。已修正包根目录脚本，并用 `Collect-Target-Pnp.ps1` 补采，候选数为 1。原始 pnp.json 保留，便于审计。

## SPI 和 GPIO 资源

原始证据是 `windows-raw/SSDT.aml` 中 GTCH.RBUF，以及 DSDT 中 SP11。`decode-resources.py` 从反汇编的 RBUF 提取字节，并断言原字节确实存在于 AML，输出 `decoded-resources.json` 和独立 RBUF.bin。

| 项目 | 本机 ACPI 声明 | Linux 对应/注意事项 |
|---|---|---|
| 触摸屏控制器 | `\_SB.SP11`，`QUP_1_SE_2,QSPI` | **spi10**，不是 spi11；Windows 名称按另一编号体系 |
| 控制器 MMIO | `0x00a88000`，长度 `0x4000` | `/soc@0/geniqup@ac0000/spi@a88000` |
| 控制器 IRQ | ACPI GSI 834 (`0x342`) | 现有 DT SPI 中断号802 (`0x322`)，加 GIC 偏移32后吻合 |
| SPI 连接 | CS0，40 MHz 上限，8 bit，CPOL0/CPHA0，CS active-low，4-wire | 这些是资源描述，不是实测时钟；不要仅改普通 SPI status 就假定可工作 |
| 设备中断 | GIO0 pin51，flags `0x13`，pull-up | falling edge / active-low，exclusive，wake-capable |
| 电源 GPIO | GIO0 pin64，IO resource，pull-down | `_PS0/_PS3` 另外直接控制 GPIO64 输出位 |
| 复位 GPIO | GI48 位于 `0x0f130000` | `_RST` 写 GPIO48，低有效复位 |
| 额外中断 | GIO0 pin896 (`0x380`)，flags `0x11`，pull-down | 意义未确认，**不能照抄成 Linux TLMM GPIO896** |

ACPI SPI 标准资源只描述四线连接，但控制器名称明确 QSPI，DSM 有 `0xEB/0xE2` opcode；需要核对现有定制 GENI QSPI/HID 驱动与额外数据线。当前 DT 的普通 spi10 pinctrl 只有 GPIO40/41/42 数据时钟、GPIO43 CS；QSPI 扩展引脚配置仍须从 Linux 定制驱动/SoC pinctrl 核实。

资源字节按 [ACPI 6.6 连接描述符规范](https://uefi.org/specs/ACPI/6.6/06_Device_Configuration.html#connection-descriptors) 解码。`PNP0C51` 与 DSM GUID 对应 [Microsoft HID over SPI 文档](https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/plug-and-play-for-spi)。

## 复位和电源时序：静态 ACPI 方法，不是总线实测

见 SSDT.dsl 的 `Device (GTCH)`：GI64=`0x0f140000`，GI48=`0x0f130000`；各 region +0 是 CFG、+4 是 IN_OUT。

- `_INI`：GPIO48输出位先清零；若 GPIO64 输出位未置位，CFG64=0x200，OUT64=2，等待10ms；随后 CFG48=0x200，OUT48=2。
- `_PS0`：若 GPIO64 输出位未置位，配置并拉高 GPIO64，等待500ms；随后配置并拉高 GPIO48。
- `_PS3`：GPIO48拉低，等待10ms，再把 GPIO64拉低。
- `_RST`：GPIO48拉低300ms，然后拉高。
- `PEP0.LPXC` 还含 GTCH 的 DSTATE 序列：D0 有 GPIO64、DELAY(0x3e8)、GPIO48、GPIO51；D3 有 GPIO48、DELAY(0x0a)、GPIO64、GPIO51。保留原文；PEP DELAY 的单位及与 ACPI 方法的执行关系未核实，不把它直接当作 Linux 毫秒参数。
- GTCH 设备块内没有 `_PR0/_PR3`，没有声明电源电压。不要凭 GPIO64 的存在猜电压数值。

## HID SPI DSM 原始返回值

GUID `6e2ac436-0fcf-41af-a265-b32a220dcfab`：revision1/function1 返回1；revision3/function0 返回0x7f（支持函数0–6）；function1=0x1000，2=0x1004，3=0x2000，4=单字节0xeb，5=单字节0xe2，6=0xa000。

这些和触摸板 HSPI 的 DSM 返回值一致，可优先检查现有已工作 `hid-over-spi` / GENI QSPI 路径能否复用；尚未读取触摸屏的实际 HID descriptor、report descriptor 或设备固件版本，不能声称协议参数已全部验证。

## 为什么之前的 I2C 探测无响应

SSDT 在 `TBID == 2 || TBID == 3` 分支定义 ITCH，HID=MSHW0468，I2C9/0x34、IRQ38、reset31、400kHz、HID descriptor address0，与 Linux 旧测试对应。`ElseIf SKID 属于0..3` 定义 GTCH/SPI。当前 Windows 的 PnP 明确实例化 GTCH/MSHW0461。未读取运行时 TBID/SKID 内存值，但实际枚举结果已经能选定本机应追踪的分支。

## Linux 下一步

1. 先读本文与原始证据。在 `/home/lucas/code/sl7-wifi-fix/` 核对当前定制驱动源码和正常 DT；撤去独立实验中的 ITCH/I2C8触摸屏节点，保留正常入口回退。
2. 当前交接 DT 中 spi10@a88000 仍 disabled；spi19@88c000 的触摸板已用 `qcom,geni-spi-qspi`、DMA protocol4、qspi read opcode0xeb、4 command bytes、8 dummy clocks。以现有实现为代码参考，审查 spi10 所需的 DMA、额外 QSPI pinmux、IRQ51和 GPIO48/64。不要原样复制触摸板 GPIO、供电或 GPI 路由。
3. 查清 pin896 的 Windows 虚拟/控制器映射；若 Linux 驱动不需要它，应写出依据。保留中断电平/边沿与驱动要求可能不同这一点，不能未经核对机械翻译。
4. 用独立、已签名的一次性测试启动项验证：控制器绑定、HID descriptor读取、input设备生成、触摸事件、休眠恢复；同时确认 WiFi/BT/USB/触摸板未回归。只在正常验证后讨论默认启动项。

## 文件与限制

完整原交接目录及 linux-evidence 已保留。`windows-raw` 包含 PnP、DSDT、一个唯一 SSDT，以及反汇编结果；Registry SSDT 与固件 API SSDT 是重复副本。Windows API 对同签名表只返回第一张，不能保证全部动态 SSDT 都采齐。

使用官方 [ACPICA 20260408](https://github.com/open-acpica/acpica/releases/tag/20260408) 的 portable iasl.exe，仅离线反汇编。初始多表 `-da` 有 AE_ALREADY_EXISTS；随后单表和外部解析成功。SSDT 用 DSDT 作外部解析；DSDT 单独反汇编有8个未解析外部方法，原始 AML 保留。不要把带外部方法推断的整份 DSL 当成可重新编译刷入的固件。

本次没有修改 Windows 驱动、设备状态、注册表、启动配置，也未写 Linux ext4 或触发 GPIO/ACPI方法。没有收集 MSDM、WiFi/BT密钥、签名私钥或输入事件。USB 拷贝包的 SHA256 位于 ZIP 同目录。
