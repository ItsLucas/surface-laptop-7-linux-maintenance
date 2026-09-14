SL7 离线采集与固件修复包 — 2026-09-14

第一次进入 Linux：
  1. 将整个 sl7-kit 文件夹从 U 盘复制到家目录。
     Ctrl+Alt+T 打开终端（图形界面不好用时 Ctrl+Alt+F3 登录）。
     ls /media/$USER
     cp -r /media/$USER/你的U盘卷名/sl7-kit ~/
  2. 执行：
     cd ~/sl7-kit
     sudo bash run.sh
  3. 采集中的 90 秒 USB 测试会显示三段提示：
     前 30 秒 USB-A；中间 30 秒靠近转轴的 USB-C；最后 30 秒另一个 USB-C。
     每段拔插已知能传数据的设备，USB-C 可翻转一次。无需按键确认。
  4. 等待修复与 initramfs 更新完成，显示 DONE 后自行重启：
     sudo reboot

重启后：
     cd ~/sl7-kit
     sudo bash run.sh after
  这次收集重启结果，并尝试正常开启 Wi-Fi、扫描热点。
  若热点出现，执行 nmtui，用方向键/Tab/Enter 连接；不需要把密码写进脚本。
  如果 USB 仍失效，可再执行 sudo bash run.sh collect，补一轮 90 秒插拔记录。

所有报告保存在 ~/sl7-diag/，每次独立保存，不覆盖旧报告。
回到 Windows 后我可以继续用 ext4 只读工具提取整个目录，不必在 Linux 下拷回 U 盘。
原始固件备份及本包修改记录保存在 /var/lib/sl7-kit/backups/。

可单独使用的命令（均在 ~/sl7-kit 内）：
  sudo bash run.sh collect    完整采集＋90秒插拔测试；不改系统设置
  sudo bash run.sh quick      完整静态采集，跳过插拔等待
  sudo bash run.sh fix        只安装 GPU、Wi-Fi 板级固件修复并更新 initramfs
  sudo bash run.sh wifi       记录 Wi-Fi 状态，解除软阻止、启用无线、扫描热点
  sudo bash run.sh undo       撤销最近一次本包固件修改，重建 initramfs；之后重启

修复内容：
  GPU：给已提取的 Romulus/qcdxkmsuc8380.mbn 建立内核实际查找的上一级路径。
  Wi-Fi：在你机器原有 board-2.bin 中，为 3378/255 的板级数据增加 1107/255 别名。
  新 Wi-Fi 文件放在 firmware/updates 下，原来的 board-2.bin.zst 保留。
  同时安装一个小型 initramfs hook，确保这两个覆盖文件进入启动镜像；undo 会移除它。
  已有冲突文件、机器型号/PCI 标识/原始固件哈希不匹配时，脚本会跳过相应修复。
  不重载驱动、不自动重启、不修改 GRUB/DTB/内核，不卸载 ADSP/CDSP。

Wi-Fi 预期：
  这一步修复已确认的“板级数据名字匹配失败”。SL7 还有独立的 rfkill 已知问题。
  如果板级错误消失，但无线仍不可用或显示 Hard blocked，需要继续处理内核层。
  rfkill unblock 只处理软阻止；本包没有把社区旧内核补丁强套进你的 7.2 内核。

采集范围：
  当前＋前三次启动内核日志、系统服务日志、设备树/DTB、GRUB与initramfs清单、
  USB控制器/PHY/运行时电源/Type-C角色/插拔事件、PMIC GLINK与remoteproc状态、
  PCI与Wi-Fi/rfkill状态、模块版本参数、固件清单哈希与板级文件、GPU/音频/输入、
  中断、时钟/电源域/稳压器/debugfs可用信息、pstore及延迟probe原因。
  缺少可选工具会记录在对应文件内，不会联网安装。每条外部命令设有超时。
  报告会含设备标识、IP/SSID与系统日志；不读取网络连接密码文件或 SSH 私钥。

如果 Linux 完全认不到 U 盘：
  USB无数据时，不能依靠挂载U盘把脚本拷入系统。
  可先在 GRUB 的 Advanced options 选择保留的 7.0.0-14 内核，尝试拷入家目录，
  再回到 7.2.0-5 执行修复。不要在旧内核执行修复后直接期待新内核initramfs已更新。
  另一个办法是沿用之前已成功的 dislocker 只读读取 Windows 分区：
  先在 Windows 将 sl7-kit 文件夹复制到 C:\sl7-kit，Linux 下执行：
     sudo mkdir -p /mnt/dislocker /mnt/windows
     sudo dislocker -r -V /dev/nvme0n1p3 -p -- /mnt/dislocker
     sudo mount -t ntfs-3g -o loop,ro /mnt/dislocker/dislocker-file /mnt/windows
     cp -r /mnt/windows/sl7-kit ~/
     cd ~/sl7-kit
     sudo bash run.sh
  dislocker 会交互询问 BitLocker 恢复密码。若已有挂载，不要重复挂载。

包内不依赖网络。常规运行只需 Ubuntu 自带 Bash/coreutils/tar/initramfs-tools，
Python 工具和原始板级文件用于复核/重建，不是安装步骤的必需依赖。
脚本使用 LF 换行，FAT/exFAT 上无需 chmod，始终通过 bash 调用。
技术依据与验证见 WIFI-研究.md 和 VALIDATION.txt。
