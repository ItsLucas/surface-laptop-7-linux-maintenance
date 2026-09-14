# Surface Laptop 7 蓝牙修复

日期：2026-09-14。系统：Ubuntu 26.10，7.2.0-5-generic。

根因：内置 WCN7850 控制器缺少 public-address，处于 Unconfigured 状态。
读取 UEFI MacAddressEmulationAddress 变量，按 https://github.com/valeronm/sl7-mac 描述的地址减一规则推导蓝牙地址，使用 btmgmt 设置后恢复。

已验证：控制器成为 Primary controller、Powered=yes；十秒发现测试成功发现周围设备。开机服务执行成功，重复运行不改变已配置控制器。尚未重启验证，也未代用户配对或连接设备。

安装文件：
- /usr/local/sbin/sl7-bt-address
- /etc/systemd/system/sl7-bt-address.service
- /etc/udev/rules.d/80-sl7-bt-address.rules

服务读取 UEFI，不写入 UEFI；仅匹配内置 WCN7850 UART，等待初始化后补充缺失地址。没有修改内核、固件、Wi-Fi 或配对记录。

撤销自动修复（不会立即关闭当前蓝牙）：

```bash
sudo systemctl disable sl7-bt-address.service
sudo rm /etc/udev/rules.d/80-sl7-bt-address.rules
sudo rm /etc/systemd/system/sl7-bt-address.service
sudo rm /usr/local/sbin/sl7-bt-address
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
```

撤销后，下次重启可能恢复为原来的未配置状态。

## 鼠标开机重连

已验证 BT5.2 Mouse 为 Paired、Bonded、Trusted、Connected，配对记录含 LongTermKey（未输出密钥）。

新增 /usr/local/sbin/sl7-mouse-connect 和 /etc/systemd/system/sl7-mouse-connect.service：开机在蓝牙服务之后最多重试约 150 秒；已连接时立即退出，不断开设备。已启用且本次执行成功。

新增 /etc/systemd/system/bluetooth.service.d/10-sl7-address.conf，确保蓝牙服务等待地址配置。/etc/bluetooth/main.conf 中明确设置 AutoEnable=true，原配置备份为 /etc/bluetooth/main.conf.before-sl7-autoconnect。未重启服务或系统，实际冷启动仍待验证。

撤销全部修复前，先禁用 sl7-mouse-connect.service，并删除上述鼠标脚本、服务和蓝牙服务 drop-in；然后按上文撤销地址服务。可从备份恢复 main.conf，但若之后有新配置，应只撤销 AutoEnable 的此次修改。
