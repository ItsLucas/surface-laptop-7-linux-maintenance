**最新实测结果：本次已启动测试镜像，但触摸屏未工作。**

触控板最终校准正常加载且哈希一致，Wi-Fi MAC跨重启正确并联网，Secure Boot和lockdown保持。触摸屏8-0034在地址探测阶段返回ENXIO；释放GPIO31复位后等50/200/800ms仍无法读取HID描述符，诊断状态已恢复。用户确认此前Windows/UEFI触摸正常，下一步核对本机Windows资源，交接目录为 `/home/lucas/code/sl7-windows-touchscreen-handoff-20260914/`。单次启动项已消费，没有安排新测试。

下面是此前获准的测试设计，保留作为历史记录。

**Romulus13 触摸屏单次测试：已获批准并安装，等待用户重启。**

测试镜像来自交接目录，SHA256 为 `d25c3487fb3374fe14de3bf56895a28d247a7ab90c532bfb31209f02b536e093`。现用镜像 SHA256 为 `5a5af0e5bbe42664d91d490b43c068b51fcb40dab71cf5712551eb142a4cc597`。

复核结果：

- PE 节中只有 `.dtbauto` 改变；内层内核、HWID、uname、SBAT 等其余节与当前启动镜像完全一致。
- 测试镜像和内层内核签名都通过已有 `SL7 Local Kernel Signing 2026` 公钥验证，该 MOK 已登记。无需再编译内核或登记新密钥。
- 设备树差异仅为启用 `i2c8`（`i2c@a80000`，400 kHz）及增加地址 `0x34` 的 `hid-over-i2c` 节点，HID 描述符地址 0，GPIO38 低电平中断，GPIO31 低有效复位。
- 现有触控板的 QSPI/GPI/HID 节点未改，Wi-Fi、蓝牙节点未改。
- `i2c_hid_of`、`i2c_hid`、`hid_multitouch`、`i2c_qcom_geni` 的已安装模块已验签。现有 initrd 包含 I2C-HID/HID-multitouch 支持，因此可复用完全相同 release 的原 initrd。
- 当前源码驱动能读取 reset GPIO，但现有 YAML binding 不允许该属性。上游审阅明确反对直接把它加入 generic binding，并提出署名问题。当前是本机功能试验，不能称为已获上游认可或通过完整 dt-schema 验证。

以下第 1–3 步已获批准并完成；第 4–5 步等待用户重启及实机验证：

1. 备份 GRUB 配置，将镜像安装到 `/boot/sl7/7.2.0-5-sl7-touchscreen-test/kernel.efi`，不覆盖现用 `kernel.efi`。
2. 安装独立脚本 `/etc/grub.d/44_sl7_touchscreen_test`，entry ID 为 `sl7-touchscreen-test`。保持 `efi=noruntime`、现有 Secure Boot 信任和 `/boot/sl7/7.2.0-5-sl7/initrd.img`。
3. 更新并检查 GRUB 配置，用 `grub-reboot sl7-touchscreen-test` 只设置下一次启动。正常默认仍为 `sl7-combined-kernel`，5 秒菜单保留。
4. 用户保存工作后重启。若测试启动失败或卡住，重新开机选择原组合内核；单次项已被 GRUB 消费后会恢复原默认。
5. 启动后核对实际 DT 节点、I2C-HID/输入日志、屏幕触摸和方向/多指输入，并回归 Wi-Fi、蓝牙、触控板及 Secure Boot。`uname -r` 仍会是 `7.2.0-5-sl7`，必须通过设备树确认进入测试镜像。

测试会首次给触摸屏执行 I2C/复位初始化，可能出现设备不响应或启动异常，因此需用户批准。当前已安装独立测试项并设置 next_entry，默认仍为正常组合内核，尚未重启。

注意：增加输入设备后 hidraw 编号可能变化。iptsd 的 udev 规则按设备识别，现有校准按 `045E:0C77` 匹配；若以后再运行人工校准，先重新定位该触控板，不能假定一直是 `/dev/hidraw1`。普通 HID-over-I2C 触摸屏不应套用 Surface Pro 11 的 SPI/IPTSD 方案。

上游来源：[说明 0/2](https://lkml.iu.edu/2609.0/14485.html)、[binding 1/2](https://lkml.iu.edu/2609.0/14487.html)、[设备树 2/2](https://lkml.iu.edu/2609.0/14488.html)、[审阅意见](https://lkml.iu.edu/2609.0/14518.html)。作者报告成功，不等于本机已经实测成功。
