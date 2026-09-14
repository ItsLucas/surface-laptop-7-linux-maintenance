**交给 Windows agent：只读核对本机 Surface Laptop 7 触摸屏资源。用中文回复。**

用户已同意把 Windows 侧需要做的工作放入此目录，并由 Windows agent 在用户重启后取回。此目录的 Linux 路径是 `/home/lucas/code/sl7-windows-touchscreen-handoff-20260914/`。当前没有要求你修改 Windows 或再自动重启。

**当前状态**

- Surface Laptop 7 13.8 英寸，X1E/Romulus13；Linux 为 Ubuntu 26.10，内核 `7.2.0-5-sl7`，Secure Boot 开启，模块和启动 MOK 已登记。
- Wi-Fi、蓝牙、触控板均需保留。触控板最终校准已确认跨重启加载，文件未丢失。用户主动关闭鼠标，鼠标自动重连服务已清理，正常蓝牙功能保留。
- Linux 当前进入的是独立触摸屏测试镜像，只比正常镜像多一小段设备树；内核本体和现有 SPI 触控板配置完全不变。
- 用户确认触摸屏此前在 Windows/Surface UEFI 正常。不要把这次失败直接判断为硬件损坏，也不要因为 Surface Pro 11 的资料而直接换成 SPI。

**Linux 已做且得到的结果**

测试设备树使用参考邮件参数：`i2c8`（QUP1 SE0，`0xa80000`，引脚32/33），400 kHz，地址0x34，HID descriptor寄存器0x0000，中断GPIO38/低电平，reset GPIO31/低有效。

设备 `8-0034` 存在，`i2c_hid_of` 已加载，但设备没有绑定驱动，也没有触摸屏 input 节点。开启限定初始化日志后重试绑定，地址探测返回 `-6 / ENXIO`；未进入 HID 描述符读取。

随后获准做了一次限定测试：在设备未绑定、GPIO31无人占用时释放复位，分别等50、200、800ms，只对0x34执行SMBus单字节读和寄存器0x0000的30字节HID描述符读取，全部ENXIO。最后将GPIO31恢复为原先的低电平并释放，调试日志设置也已恢复。没有扫描其他I2C地址、修改固件、加载新驱动或增加新的启动项。

因此现在需要本机的真实 Windows/ACPI 资源，确认参考参数是否完整且适配该面板/触控控制器。不要继续猜测电源GPIO、电压或大范围扫总线。

**请执行的工作**

1. 如已进入 Windows，先记录触摸屏当前是否可用（需要时让用户实际触摸；不能用驱动状态代替手指测试）。
2. 审阅并运行本目录 `Collect-SL7-Touchscreen.ps1`。默认在桌面创建 `SL7-touchscreen-日期时间` 文件夹，输出触摸屏PnP候选及父设备链、HID元数据、DSDT/首个SSDT和可用的ACPI注册表副本。
3. 若脚本权限不足，说明具体失败；不要关闭Secure Boot、开启测试签名、安装采集内核驱动或修改全局执行策略。系统API/允许的只读注册表访问优先。脚本尚未在Windows实测，请核对输出是否完整。
4. 从输出定位真正的触摸屏，不要混入Touchpad/触控板或触控笔。重点记录硬件/兼容ID、ACPI父设备及LocationPaths、使用的Windows驱动/INF。
5. 若具备可信的ACPICA反编译工具，可将DSDT/SSDT转为ASL，并保留原始AML。核对目标设备的 `_HID`/`_CID`/`_UID`、`_CRS` 中的I2C地址/控制器路径/频率/IRQ、`_DSM` 中的HID描述符地址，以及 `_PR0`/`_PR3`、`_PS0`/`_PS3`、电源资源方法中的GPIO、复位极性、使能线和延时。
6. 用实际资源与Linux测试参数逐项比较，写一份 `WINDOWS-FINDINGS.zh-CN.md`，区分已确认和未确认。连同原始输出放回这个交接目录下的 `results/`，或记录 Windows 输出路径供用户/后续Linux agent取回。只记录诊断，不修改驱动/固件/启动设置。

运行示例（从脚本所在目录）：

```powershell
powershell.exe -NoProfile -File .\Collect-SL7-Touchscreen.ps1
```

`GetSystemFirmwareTable` 对同名SSDT只返回第一张，因此脚本还尝试只读 `HKLM\HARDWARE\ACPI\DSDT` 和 `...\SSDT` 的合法表副本。它不保证取齐所有SSDT；缺失时明确说明，不安装需要绕过签名的驱动来抓取。

**参考与交接路径**

- 参考补丁：[0/2](https://lkml.iu.edu/2609.0/14485.html)、[binding](https://lkml.iu.edu/2609.0/14487.html)、[设备树](https://lkml.iu.edu/2609.0/14488.html)、[审阅意见](https://lkml.iu.edu/2609.0/14518.html)。这是参考，不是本机资源证明；generic binding里的reset-gpios也存在上游反对意见。
- `linux-evidence/` 有实际启动报告、错误日志、复位诊断、设备树完整反编译与差异。
- Linux工程 `/home/lucas/code/sl7-wifi-fix/`；维护工程 `/home/lucas/code/sl7-maintenance-20260914/`。
- 正常默认仍为 `sl7-combined-kernel`，本次 `sl7-touchscreen-test` 单次选择已消费，没有安排再次试启动。

采集内容不包括Wi-Fi认证、蓝牙配对密钥、签名私钥或按键/触摸事件。ACPI表只选DSDT/SSDT，不采集含Windows产品密钥的MSDM表。不要向公开仓库上传本机原始信息。
