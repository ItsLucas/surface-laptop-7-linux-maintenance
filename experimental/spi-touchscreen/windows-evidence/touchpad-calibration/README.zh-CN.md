# Windows 触摸板参数提取

已从本机 MSHW0238 触摸板导出 30 个注册表值、3 个原始二进制，以及当前实际加载的 Surface TouchPad Processor 驱动包（DLL/INF/CAT）。采集脚本在上一层 Collect-Touchpad-Calibration.ps1，完全只读。没有运行 DLL 或改变 Windows 的校准。

最有价值的文件是 `001-CurrentParams.bin`（119 bytes），来源：

`HKLM\SYSTEM\CurrentControlSet\Enum\HID\MSHW0238&COL02\3&868ECB2&0&0001\Device Parameters\Heat\CurrentParams`

从偏移14开始的105字节与 iptsd 的 metadata::Frame 结构完全对齐。按该结构解码：18行、26列；物理宽度12000/高度8000（单位0.01mm，即120×80mm）；变换矩阵 xx=480、yy≈470.588226，其余4项为0。两轴步长分别乘25/17后吻合物理尺寸。前14字节Windows包装语义未全部确认，所以这是有交叉校验的结构解释，而不是已验证的Windows格式规范。

`decoded-current-params.json` 包含全部解码结果；`decode-current-params.py` 可在 Linux 离线复跑。后面的16个浮点数按 iptsd 上游仍属于 Unknown，不能未经证据当作手指大小、防误触或倾斜校准系数。

对照的 [iptsd 源码](https://github.com/linux-surface/iptsd) 已保存，确切commit在 iptsd-source-commit.txt：protocol/metadata.hpp 定义结构和单位，parser.hpp 将物理尺寸转换成厘米，并从xx/yy符号取得是否反转；config-loader.hpp 接受 Config/Width、Height、InvertX、InvertY，也会默认从设备读取元数据。可先比较 Linux 启动日志/现有配置，若已经得到12×8cm且方向正确，则无需增加覆盖。

附 `92-windows-touchpad-geometry.conf.example` 仅供 Linux agent 核对后使用，限定设备045E:0C77，未自动安装；它提供几何参数，不覆盖 Contacts 校准。需要先核对本机定制 iptsd 版本与已工作触摸板的方向，不能只因文件存在就安装。

**没有找到可直接导入 iptsd 的 Windows SizeMin/SizeMax/AspectMin/AspectMax 校准。** [iptsd官方校准说明](https://github.com/linux-surface/iptsd/wiki/Calibrating-iptsd) 中这些参数是通过用户手指接触采样得到的尺寸/宽高比阈值。原 Linux 交接已经确认当前设备加载 `/etc/iptsd.d/91-calibration-045E-0C77.conf`：0.8/2.0/1.0/2.1；暂时保留这份已验证配置，不用Windows未知浮点数替换。

registry.json 还包括Windows指针速度、手势和AAP/curtain设置。这些不是iptsd原生校准字段，没有执行直接映射。FastHostId、LatestFwVersion仅按原始字节保留，没有猜测固件版本编码。

TouchPenProcessor0C77.dll 是 Windows 实际注册的触摸板处理器（约9.5MB），Authenticode验证成功；INF版本为27.16.139.0。DLL仅作为后续离线分析证据，iptsd不能直接加载它。未发现同目录独立的校准配置文件；更深层的设备内校准或DLL内嵌算法仍未解码。该文件是本机专有驱动的副本，交接包供本机迁移分析使用。
