# Surface Laptop 7 触控板停顿：Windows 对照采集

请用中文继续。用户已允许把 Windows 所需工作放入目录，由 Windows agent 获取。此目录只用于采集/对照，不授权更新固件、改驱动、改安全设置或自动重启。

硬件为 Surface Laptop 7 13.8 英寸 Romulus13，触控板 MSHW0238 / 045E:0C77。Linux 已能移动、物理点击、轻触、双指操作，但快速连续物理按压易触发短时停顿；用户报告停顿时有时同时没有震感，键盘正常，稍后自行恢复。Linux 原 iptsd 和点击修复候选均发生过，不能只归咎于候选。

## Linux 已确认

- 三批 SPI 跟踪共 40,722 条消息均有完成事件，没有遗留未完成消息，缓冲无丢事件；最长提交到完成约19.514ms。这些完成事件不等于对每个字节内容做过校验。
- 用户标记卡住期间，多次看到 SPI/DMA/HID 仍持续运行，真实 SPI 控制器 active；没有总线错误或设备复位记录。自动休眠对照未执行，当前暂停这一方案。
- 正常 HID report ID0x0a 长1000字节，有效内部HID frame约750字节，包含468字节热图（18×26）及若干状态报告，常见子报告flags=0x04。
- 标记卡住时，ID0x0a外层仍1000字节，但有效内部帧缩到262/282字节，仅有状态报告；热图子帧消失，维度仍18×26。多数flags变为0x08，新增type0x12（payload长度4或24）。type0x94的现有按钮bit解析为0。恢复后热图返回。
- iptsd解析器错误计数为0；卡住时没有热图回调，因此不是本次Contacts阈值简单过滤了已有热图中的触点。
- flags0x08/type0x12的语义未确认，不得直接称为过流、噪声保护、固件损坏或标准HID多点模式；0x12也可能包含另一种可用数据，需要证据解码。

精简正常/卡住/恢复样例和验证汇总在linux-evidence。未保存完整热图或运动坐标。

## Windows 需要做的工作

1. 先运行本目录Collect-Touchpad-State.ps1，读取目标触控板PnP、版本和精确设备参数，发现可用ETW提供者。脚本只写results文件；未在Windows实际验证，遇到缺项应报告，不要自动补装工具或改注册表。
2. 用正常力度、能复现Linux现象的连续物理点击方式，在Windows对照移动、震感是否同样短暂停止。记录开始、卡住、恢复的准确时间，说明是否一直在操作。无需极端用力。
3. 检查目标触控板/Surface Heat处理器是否提供可读状态或针对性的ETW事件。优先用系统已有工具，仅启用已确认属于本触控板/处理器的提供者；不要采集全局键盘、网络或认证内容。若无法找到提供者或字段，直接记录未知，不要猜GUID/寄存器/IOCTL，也不要使用内核调试或注入程序。
4. 本机提供的TouchPenProcessor0C77.dll静态字符串中存在：TouchpadHapticOvercurrentEvent、StoppedDueNoiseCount、TransitionsToPhoenixLikeModeCounter、PhoenixHastaTransitionsCounter、TouchDetectionNoValidFullFrameNorBlobSection。这些只是核对线索，不是本次故障的已知状态或字段映射。尝试从实际诊断事件/公开符号确认是否有相关计数在复现前后变化，以及0x12/flags0x08的含义。
5. 将原始采样、操作时间线、Windows是否复现、字段定义依据及结论写入results。明确区分事实、推断、未知。不要仅转述上述字符串便认定故障原因。

如果确需额外有风险的硬件操作、更新固件或重启，先向用户说明具体动作并询问；现有Linux Secure Boot、MOK、Wi-Fi、蓝牙和触控板必须保留。

当前Linux仍是7.2.0-5-sl7 + iptsd3.1.0+sl7.1，轻触点击开启，最终指尖/拇指校准不变。点击候选3.1.0+sl7.2已通过三轮各10点击/0双击，但未永久安装。SPI触摸屏独立单次启动项已经另行获准安排，默认正常镜像保留；不要修改这些启动项。
